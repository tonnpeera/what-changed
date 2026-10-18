#!/usr/bin/env python3
"""Re-open every `read` source and check its quote really is on the page.

Usage: python3 verify_quotes.py <store-dir | ledger.md ...> [--timeout 20]
Deterministic: plain HTTP GET + text normalisation, no model involved.
Reports found / checkable. Pages that cannot be fetched
are listed separately as unreachable, not counted as failures; pages that
render their text with JavaScript will show as "not found" and need a
manual look. Standard library only.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprint import strip_markup, sub_tags, unescape  # noqa: E402
from ledger import parse_ledger, scoped_ledger_files  # noqa: E402
from net import fetch  # noqa: E402

TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ", "…": "...",
})


def normalise(text: str) -> str:
    text = unescape(text).translate(TRANSLATE).lower()
    text = re.sub(r"[`*_>#|\\]", "", text)
    text = unlink(text)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r" ([.,;:!?)\]])", r"\1", text).strip()  # "costs <b>$5</b>." -> "costs $5."


def unlink(text: str) -> str:
    r"""Markdown links -> text: re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text) in linear time
    (that regex rescans to the next "]" or ")" from every "[" that does not start a link)."""
    out, pos, at = [], 0, 0
    while (i := text.find("[", at)) != -1 and (j := text.find("]", i + 1)) != -1:
        k = text.find(")", j + 2) if text.startswith("(", j + 1) else -1
        if k == -1:
            if text.startswith("(", j + 1):
                break  # no ")" after this "](", so none after a later one
            at = j + 1  # every "[" before j finds the same "]" and fails the same way
            continue
        out += [text[pos:i], text[i + 1:j]]
        pos = at = k + 1
    return "".join(out) + text[pos:]


def quote_key(quote: str) -> str:
    """A quote may end where the sentence continues ("root." vs "root, so ..."):
    compare without trailing punctuation."""
    return normalise(quote).rstrip(".,;:!?")


def looks_like_html(raw: str) -> bool:
    head = raw[:2000].lower()
    return any(tag in head for tag in ("<!doctype html", "<html", "<head", "<body", "<div"))


def page_text(raw: str) -> str:
    if looks_like_html(raw):  # leave Markdown/plain text alone: `<skill-name>` is content there
        raw = strip_markup(raw, tags=False)
        # Inline tags sit inside words in languages written without spaces (Thai, Chinese,
        # Japanese), so drop them without adding a space; other tags end a block of text.
        raw = sub_tags(r"(?is)</?(?:a|abbr|b|bdi|bdo|cite|code|data|dfn|em|font|i|kbd|mark|q|s|samp|small|span|strong|sub|sup|time|u|var|wbr)\b[^>]*>", "", raw)
        raw = sub_tags(r"(?s)<[^>]+>", " ", raw)
    return normalise(raw)


def is_pdf(url: str, r) -> bool:
    return (getattr(r, "content_type", "") == "application/pdf" or url.lower().split("?")[0].endswith(".pdf")
            or (r.text or "").lstrip().startswith("%PDF"))


def main(argv: list[str]) -> int:
    timeout = 20.0
    args = argv[1:]
    if "--timeout" in args:
        i = args.index("--timeout")
        timeout = float(args[i + 1])
        del args[i:i + 2]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    paths, why = scoped_ledger_files(args)
    if why:
        print(why)
        return 2

    # Group quotes by URL so every quote on one page gets the same page state.
    by_url: dict[str, list[tuple[str, str, str]]] = {}
    no_quote = 0
    for path in paths:
        for claim in parse_ledger(path).claims:
            for s in claim.sources:
                if s.how != "read":
                    continue
                if not s.quote:
                    no_quote += 1
                    continue
                by_url.setdefault(s.url, []).append((path.name, claim.id, s.quote))

    found = checkable = 0
    missing: list[str] = []
    truncated: list[str] = []
    unreachable: list[str] = []
    unsupported: list[str] = []
    for url, quotes in by_url.items():
        r = fetch(url, timeout)
        if r.text is not None and is_pdf(url, r):
            unsupported += [f"{f} {cid} {url} (pdf)" for f, cid, _ in quotes]
            continue
        text = page_text(r.text) if r.text is not None else None
        status = r.status
        if text is not None and any(quote_key(q) not in text for _, _, q in quotes):
            # Pages can arrive incomplete or vary between loads: fetch once more, keep the longer copy,
            # and treat the page as partial if either copy was.
            r2 = fetch(url, timeout)
            if r2.text is not None:
                text2 = page_text(r2.text)
                if len(text2) > len(text):
                    text = text2
                if "partial" in (status, r2.status):
                    status = "partial"
        if text is None:
            unreachable += [f"{f} {cid} {url} ({status})" for f, cid, _ in quotes]
            continue
        for f, cid, q in quotes:
            if quote_key(q) in text:
                found += 1
                checkable += 1
            elif status == "partial":
                truncated.append(f"{f} {cid} {url}")
            else:
                checkable += 1
                missing.append(f'{f} {cid} {url}\n      quote: "{q}"')

    print(f"verify_quotes: {found}/{checkable} quotes found on their page")
    print(f"  unreachable (not counted): {len(unreachable)} · download truncated, quote not in the part received (not counted): {len(truncated)} · pdf, not checkable by this script (not counted): {len(unsupported)} · read sources without a quote: {no_quote}")
    for m in missing:
        print(f"  NOT FOUND {m}")
    for u in unreachable:
        print(f"  UNREACHABLE {u}")
    for t in truncated:
        print(f"  TRUNCATED {t}")
    for u in unsupported:
        print(f"  UNSUPPORTED {u}")
    return 0 if found == checkable and no_quote == 0 else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
