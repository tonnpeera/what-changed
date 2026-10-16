#!/usr/bin/env python3
"""Check ledger files against the format and the confidence ceilings.

Usage: python3 check_ledger.py <store-dir | ledger.md ...>
Prints passed/total per rule and each failure. Given a store folder, it also checks that the
run times in runs.log and in the digests' "## Run HH:MM" headings are not later than the
files were written (a time the agent made up rather than read from the clock).
Exit code 1 if any rule fails. Standard library only; no network.
"""
from __future__ import annotations

import io
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger import parse_ledger, scoped_ledger_files  # noqa: E402

STATUSES = {"active", "superseded", "retracted", "disputed"}
LEVELS = ["very-low", "low", "medium", "high"]
REQUIRED = ["status", "confidence", "sources"]
# Thai, Lao, Khmer, Myanmar, CJK, kana, hangul: scripts written without spaces between words.
NO_SPACE_SCRIPT = re.compile(r"[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
# Must stay in step with precheck.SOURCE_STATE.
SOURCE_STATE_LINE = re.compile(r'^- (\S+)(?: (?:→|->) \S+)? — fingerprint: "?(.*?)"? — checked: (\S+)')
RUN_HEADING = re.compile(r"^## Run (\d\d):(\d\d)\b", re.M)
# A claim that replaces another must say when the new value took effect (SKILL.md step 4).
EFFECTIVE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b|effective date not stated", re.I)
CLOCK_SLACK = timedelta(minutes=2)


def level_of(confidence: str) -> str | None:
    words = confidence.split("—")[0].split()
    return words[0] if words and words[0] in LEVELS else None


def ceiling(sources) -> str:
    if not sources:
        return "very-low"
    if all(s.tier == "T4" for s in sources):
        return "very-low"
    if not any(s.how == "read" for s in sources):
        return "low"
    if not any(s.how == "read" and s.tier in ("T1", "T2", "T3") for s in sources):
        return "low"
    if not any(s.how == "read" and s.tier == "T1" for s in sources):
        return "medium"
    return "high"


def valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def written_at(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone()


def run_times(store: Path):
    """(rule, ok, where, why) for every run time in runs.log and today's-date digests."""
    rule = "run times are not later than the file was written"
    log = store / "runs.log"
    if log.is_file():
        limit = written_at(log) + CLOCK_SLACK
        for n, line in enumerate(log.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stamp = line.split("\t", 1)[0].strip()
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                continue  # a date only, or "T--:--": no time was claimed
            when = when if when.tzinfo else when.astimezone()
            yield rule, when <= limit, f"runs.log:{n}", f"{stamp} is after the file was last written ({limit - CLOCK_SLACK:%Y-%m-%dT%H:%M})"
    for digest in sorted((store / "digests").glob("*.md")) if (store / "digests").is_dir() else []:
        mtime = written_at(digest)
        if digest.stem != mtime.date().isoformat():
            continue  # written on another day (or copied): HH:MM alone cannot be compared
        limit = mtime.replace(tzinfo=None) + CLOCK_SLACK
        text = digest.read_text(encoding="utf-8", errors="replace")
        for m in RUN_HEADING.finditer(text):
            when = datetime.fromisoformat(f"{digest.stem}T{m.group(1)}:{m.group(2)}")
            n = text.count("\n", 0, m.start()) + 1
            yield rule, when <= limit, f"digests/{digest.name}:{n}", f"Run {m.group(1)}:{m.group(2)} is after the file was last written ({mtime:%H:%M})"


def check(paths: list[Path], stores: list[Path] = ()) -> tuple[dict[str, list[int]], list[str]]:
    results: dict[str, list[int]] = {}
    failures: list[str] = []

    def record(rule: str, ok: bool, where: str, why: str = "") -> None:
        passed_total = results.setdefault(rule, [0, 0])
        passed_total[1] += 1
        if ok:
            passed_total[0] += 1
        else:
            failures.append(f"{where}: {rule}{' — ' + why if why else ''}")

    for path in paths:
        ledger = parse_ledger(path)
        ids = [c.id for c in ledger.claims]
        text = path.read_text(encoding="utf-8", errors="replace")
        state = re.search(r"^## Source state\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        for line in (state.group(1).splitlines() if state else []):
            if line.startswith("- "):
                record("Source state lines readable by precheck", bool(SOURCE_STATE_LINE.match(line)), str(path.name), line[:80])
        record("ledger has frontmatter topic", "topic" in ledger.frontmatter, str(path))
        for claim in ledger.claims:
            where = f"{path.name}:{claim.line_no} {claim.id}"
            record("claim id unique", ids.count(claim.id) == 1, where)
            missing = [f for f in REQUIRED if f not in claim.fields]
            record("required fields present", not missing, where, f"missing {missing}")
            status = claim.fields.get("status", "").split()[0] if claim.fields.get("status") else ""
            record("status valid", status in STATUSES, where, status)
            if status == "superseded":
                target = claim.fields.get("superseded_by", "").strip()
                record("superseded claim points to an existing claim", target in ids, where, target or "empty")
                newer = next((c for c in ledger.claims if c.id == target), None)
                if newer is not None:
                    record("a claim that replaces another states when it took effect", bool(EFFECTIVE.search(newer.text)),
                           f"{path.name}:{newer.line_no} {newer.id}", "no date (or \"effective date not stated\") in its heading")
            record("every source line parses", not claim.unparsed_source_lines, where,
                   "; ".join(f"line {n}" for n, _ in claim.unparsed_source_lines))
            record("has at least one source", bool(claim.sources), where)
            for s in claim.sources:
                record("source has a tier T1-T4", s.tier is not None, f"{path.name}:{s.line_no}")
                if s.how == "read":
                    record("read source has a verbatim quote", bool(s.quote), f"{path.name}:{s.line_no}")
                    if s.quote:
                        if NO_SPACE_SCRIPT.search(s.quote):
                            record("quote is at most 25 words (150 characters without spaces)", len(s.quote) <= 150,
                                   f"{path.name}:{s.line_no}", f"{len(s.quote)} characters")
                        else:
                            record("quote is at most 25 words (150 characters without spaces)", len(s.quote.split()) <= 25,
                                   f"{path.name}:{s.line_no}", f"{len(s.quote.split())} words")
            level = level_of(claim.fields.get("confidence", ""))
            record("confidence level valid", level is not None, where, claim.fields.get("confidence", ""))
            if level:
                cap = ceiling(claim.sources)
                ce = claim.fields.get("counter-evidence", claim.fields.get("counter_evidence", "")).lower()
                if not ce.strip() or "not searched" in ce or "not yet" in ce:
                    cap = min(cap, "medium", key=LEVELS.index)
                record("confidence within ceiling", LEVELS.index(level) <= LEVELS.index(cap), where,
                       f"{level} > ceiling {cap}")
            for key, value in claim.dates.items():
                record("dates are ISO", valid_date(value), where, f"{key}={value}")
    for store in stores:
        for rule, ok, where, why in run_times(store):
            record(rule, ok, where, why)
    return results, failures


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) > 1 else 2
    paths, why = scoped_ledger_files(argv[1:])
    if why:
        print(why)
        return 2
    if not paths:
        print("no ledger files found")
        return 2
    stores = [Path(a) for a in argv[1:] if Path(a).is_dir() and (Path(a) / "topics.yaml").is_file()]
    results, failures = check(paths, stores)
    total_pass = sum(p for p, _ in results.values())
    total = sum(t for _, t in results.values())
    print(f"check_ledger: {total_pass}/{total} checks passed across {len(paths)} ledger(s)")
    for rule, (p, t) in results.items():
        print(f"  {p}/{t}  {rule}")
    if failures:
        print("failures:")
        for f in failures:
            print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
