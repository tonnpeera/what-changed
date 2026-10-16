"""Parse what-changed ledger files. Standard library only.

Used by check_ledger.py and verify_quotes.py; importable on its own.
"""
from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

CLAIM_HEADING = re.compile(r"^###\s+(C-\d{3,})\s+·\s+(.+?)\s*$")
FIELD = re.compile(r"^-\s+([a-z_-]+):\s*(.*)$")
SOURCE = re.compile(
    r"^\s+-\s+\[(?P<label>[^\]]*)\]\((?P<url>[^)\s]+)\)"
    r"(?:\s+—\s+(?P<tier>T[1-4]))?"
    r"\s+—\s+(?P<how>read|search-snippet|unverified)"
    r"(?:\s+—\s+quote:\s+\"(?P<quote>.*)\")?\s*$"
)
DATE_FIELD = re.compile(r"(first_seen|last_confirmed|review_by):\s*(\S+)")


@dataclass
class Source:
    label: str
    url: str
    tier: str | None
    how: str
    quote: str | None
    line_no: int


@dataclass
class Claim:
    id: str
    text: str
    line_no: int
    fields: dict[str, str] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    unparsed_source_lines: list[tuple[int, str]] = field(default_factory=list)
    dates: dict[str, str] = field(default_factory=dict)


@dataclass
class Ledger:
    path: Path
    frontmatter: dict[str, str]
    claims: list[Claim]


def parse_ledger(path: Path) -> Ledger:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()  # agent-written: never crash on bytes
    frontmatter: dict[str, str] = {}
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            if ":" in lines[i]:
                k, v = lines[i].split(":", 1)
                frontmatter[k.strip()] = v.strip().strip('"')
            i += 1
        i += 1

    claims: list[Claim] = []
    current: Claim | None = None
    in_sources = False
    for n in range(i, len(lines)):
        line = lines[n]
        m = CLAIM_HEADING.match(line)
        if m:
            current = Claim(id=m.group(1), text=m.group(2), line_no=n + 1)
            claims.append(current)
            in_sources = False
            continue
        if current is None:
            continue
        if line.startswith("#"):
            current = None
            continue
        fm = FIELD.match(line)
        if fm:
            key, value = fm.group(1), fm.group(2)
            current.fields[key] = value
            in_sources = key == "sources"
            for dk, dv in DATE_FIELD.findall(line):
                current.dates[dk] = dv
            continue
        if in_sources and line.startswith("  -"):
            sm = SOURCE.match(line)
            if sm:
                current.sources.append(
                    Source(
                        label=sm.group("label"),
                        url=sm.group("url"),
                        tier=sm.group("tier"),
                        how=sm.group("how"),
                        quote=sm.group("quote"),
                        line_no=n + 1,
                    )
                )
            else:
                current.unparsed_source_lines.append((n + 1, line))
    return Ledger(path=path, frontmatter=frontmatter, claims=claims)


class UnsafeWrite(Exception):
    pass


# Neither flag exists on Windows, where FIFOs and these symlink races do not apply the same way.
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


def unsafe_target(store: Path, path: Path) -> str | None:
    """Why writing `path` (below `store`) could land somewhere else, or None. Agents on some hosts
    can write anywhere in the project, so a planted symlink (runs.log -> ~/.zshrc), a symlinked
    folder on the way, or a hard link to a file elsewhere would make a script that runs outside
    any sandbox write into that file."""
    current = store
    for part in path.relative_to(store).parts:
        current = current / part
        if current.is_symlink():
            return f"{current} is a symlink"
    if path.exists() and (not path.is_file() or path.stat().st_nlink > 1):
        return f"{path} is not a plain file with a single link"
    return None


def open_in_store(store: Path, path: Path, append: bool):
    """Open `path` below `store` for writing, folder by folder relative to the one opened before
    (dir_fd) with O_NOFOLLOW, so no symlink can be followed or swapped in on the way; missing
    folders are created. Refuses files with more than one hard link before truncating anything."""
    parts = path.relative_to(store).parts
    if not parts:
        raise UnsafeWrite(f"{path} is the store itself, not a file in it")
    # O_NONBLOCK: opening a FIFO for writing would otherwise wait forever for a reader (ENXIO instead).
    flags = os.O_WRONLY | os.O_CREAT | _NONBLOCK | _NOFOLLOW | (os.O_APPEND if append else 0)
    try:
        if os.open not in os.supports_dir_fd:  # Windows: check, then open by path
            why = unsafe_target(store, path)
            if why:
                raise UnsafeWrite(why)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, flags, 0o644)
        else:
            folder = os.open(store, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for part in parts[:-1]:
                    try:
                        os.mkdir(part, 0o755, dir_fd=folder)
                    except FileExistsError:
                        pass
                    sub = os.open(part, os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW, dir_fd=folder)
                    os.close(folder)
                    folder = sub
                fd = os.open(parts[-1], flags, 0o644, dir_fd=folder)
            finally:
                os.close(folder)
    except OSError as e:  # ELOOP or ENOTDIR when a symlink is in the way, ENXIO for a FIFO
        raise UnsafeWrite(f"cannot write {path} safely: {e.strerror}") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
            raise UnsafeWrite(f"{path} is not a plain file with a single link")
        if not append:
            os.ftruncate(fd, 0)
    except BaseException:
        os.close(fd)
        raise
    return os.fdopen(fd, "a" if append else "w", encoding="utf-8", newline="\n")  # same bytes on every OS


def outside_store(path: Path) -> str | None:
    """The store, if WHAT_CHANGED_STORE is set (the schedulers set it for the agent) and path,
    after following symlinks and "..", is not inside it; else None."""
    store = os.environ.get("WHAT_CHANGED_STORE")
    if not store:
        return None
    try:
        inside = path.resolve().is_relative_to(Path(store).resolve())
    except (OSError, RuntimeError):
        inside = False
    return None if inside else store


def scoped_ledger_files(args: list[str]) -> tuple[list[Path], str | None]:
    """ledger_files() for each argument, or ([], why) if any argument or file found is outside
    WHAT_CHANGED_STORE. Checked before anything is read, so nothing outside is listed or opened."""
    paths: list[Path] = []
    for arg in args:
        store = outside_store(Path(arg))
        if store:
            return [], f"refused: {arg} is outside the store ({store})"
        for f in ledger_files(Path(arg)):
            store = outside_store(f)
            if store:
                return [], f"refused: {f.name} in {arg} points outside the store ({store})"
            paths.append(f)
    return paths, None


def ledger_files(store: Path) -> list[Path]:
    """Accept a store folder (uses ledger/*.md) or individual ledger files."""
    if store.is_file():
        return [store]
    folder = store / "ledger" if (store / "ledger").is_dir() else store
    return sorted(f for f in folder.glob("*.md") if f.is_file())
