#!/usr/bin/env python3
"""Cheap "did this source change?" signal for one or more URLs.

Usage: python3 fingerprint.py URL [URL ...] [--timeout 20] [--budget 600]
Prints one JSON object per URL (URLs left when --budget seconds have passed are not fetched;
their "detail" says so):
  {"url", "ok", "kind", "fingerprint", "detail", "partial", "final_url"}
kind is one of: release-feed, feed, changelog, page.
- GitHub repo releases URL  -> newest tag from the releases Atom feed
- RSS/Atom                  -> newest item's date + title
- Markdown changelog        -> first version-like heading
- Any other page            -> <title> + first <h1> + short hash of the text
Page hashes can change for reasons that are not news (ads, timestamps):
treat a page-hash change as "look", not as "something happened".
Standard library only.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import re
import sys
import time
from pathlib import Path

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import encode_url as net_encode, fetch  # noqa: E402

VERSION_HEADING = re.compile(r"^#{1,4}\s*\[?v?(\d+\.\d+(?:\.\d+)?[^\s\]]*)", re.M)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_HEADING = re.compile(rf"^#{{1,4}}\s*((?:{MONTHS}) \d{{1,2}}, \d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\s*$", re.M)
BLOCK_OPEN = re.compile(r"<(script|style|noscript)\b", re.I)
# Characters str.splitlines() breaks on. A raw one is collapsed as whitespace; one written as an
# entity (&#10;) appears only after unescaping and would put a page-made line into the digest.
LINE_BREAKS = re.compile(r"[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]+")

# Page markup is untrusted and up to net.MAX_BYTES long. A regex like <title[^>]*>(.*?)</title>
# retries every later "<title" to the end of the text when the closing tag is missing, which is
# quadratic: the helpers below give the same results in one pass.


def sub_tags(pattern: str, repl: str, text: str) -> str:
    """re.sub for a pattern whose matches end at the first ">" after a "<": nothing after the
    last ">" can match, so leave it out rather than rescan it from every unclosed "<"."""
    k = text.rfind(">") + 1
    return re.sub(pattern, repl, text[:k]) + text[k:]


def strip_markup(text: str, tags: bool = True) -> str:
    """Same as re.sub(r"(?is)<(script|style|noscript)\\b.*?</\\1>|<[^>]+>", " ", text) (without the
    <[^>]+> part when tags is False), in linear time."""
    out, pos, at = [], 0, 0
    last_gt = text.rfind(">")
    unclosed: set[str] = set()  # no closing tag after one opening means none after a later one
    while (i := text.find("<", at)) != -1 and i < last_gt:
        end = -1
        m = BLOCK_OPEN.match(text, i)
        if m and m.group(1).lower() not in unclosed:
            close = re.compile(f"</{m.group(1)}>", re.I).search(text, m.end())
            if close:
                end = close.end()
            else:
                unclosed.add(m.group(1).lower())
        if end < 0 and tags and text[i + 1] != ">":
            end = text.find(">", i + 1) + 1
        if end < 0:
            at = i + 1
            continue
        out += [text[pos:i], " "]
        pos = at = end
    return "".join(out) + text[pos:]


def first(open_tag: str, close_tag: str, text: str) -> str:
    """Text of the first open_tag...close_tag element, as re.search(open_tag + r"[^>]*>(.*?)" +
    close_tag) finds it, on one line."""
    m = re.search(open_tag, text, re.I)
    gt = text.find(">", m.end()) if m else -1
    end = re.compile(close_tag, re.I).search(text, gt + 1) if gt >= 0 else None
    if not end:
        return ""
    inner = text[gt + 1:end.start()]
    k = inner.rfind(">") + 1
    inner = re.sub(r"<[^>]+>|\s+", " ", inner[:k]) + re.sub(r"\s+", " ", inner[k:])
    return LINE_BREAKS.sub(" ", unescape(inner)).strip()


def unescape(text: str) -> str:
    """html.unescape, which raises ValueError for a decimal character reference longer than
    int()'s digit limit (4,300 digits); a reference that long is never a real character."""
    try:
        return html.unescape(text)
    except ValueError:  # same result: drop leading zeros, and any value over 8 digits is U+FFFD anyway
        return html.unescape(re.sub(r"&#0*([0-9]+;?)", lambda m: "\ufffd" if len(m.group(1).rstrip(";")) > 7
                                    else "&#" + m.group(1), text))


def from_feed(text: str) -> tuple[str, str]:
    m = re.search(r"<(?:item|entry)\b", text, re.I)
    end = re.compile(r"</(?:item|entry)>", re.I).search(text, m.end()) if m else None
    item = text[m.end():end.start()] if m and end else ""
    title = first(r"<title", r"</title>", item)
    when = first(r"<(?:updated|pubDate|published|dc:date)", r"</", item)
    if not item:
        return "(no items)", "feed has no entries"
    return f"{when} | {title}".strip(" |"), "newest item"


def fingerprint(url: str, timeout: float, total: float | None = None) -> dict:
    """total: seconds the fetch may take in all (net.fetch's default when None)."""
    target = url
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/releases/?$", url)
    if m:
        target = f"https://github.com/{m.group(1)}/{m.group(2)}/releases.atom"
    r = fetch(target, timeout, total=total)
    if r.text is None:
        return {"url": url, "ok": False, "kind": None, "fingerprint": None, "detail": r.status,
                "partial": False, "final_url": r.final_url or url}
    result = _classify(url, r.text, bool(m))
    result["partial"] = r.status == "partial"
    result["final_url"] = r.final_url or target
    if result["partial"]:
        result["detail"] += f" (download truncated: {r.received} of {r.expected or '?'} bytes; a page hash is not comparable)"
    if not m and r.final_url and r.final_url.rstrip("/") != net_encode(url).rstrip("/"):
        result["detail"] += f" (redirected to {r.final_url}: check the watchlist URL)"
    return result


def _classify(url: str, text: str, is_release: bool) -> dict:
    head = text[:500].lower()
    if is_release:
        fp, detail = from_feed(text)
        return {"url": url, "ok": True, "kind": "release-feed", "fingerprint": fp, "detail": detail}
    if "<rss" in head or "<feed" in head:
        fp, detail = from_feed(text)
        return {"url": url, "ok": True, "kind": "feed", "fingerprint": fp, "detail": detail}
    vm = VERSION_HEADING.search(text)
    if vm and "<html" not in head:
        return {"url": url, "ok": True, "kind": "changelog", "fingerprint": vm.group(1),
                "detail": "first version heading"}
    dm = DATE_HEADING.search(text)
    if dm and "<html" not in head:
        return {"url": url, "ok": True, "kind": "changelog", "fingerprint": dm.group(1),
                "detail": "first dated heading"}
    title = first(r"<title", r"</title>", text)
    h1 = first(r"<h1", r"</h1>", text)
    body = strip_markup(text)
    digest = hashlib.sha256(re.sub(r"\s+", " ", body).encode()).hexdigest()[:12]
    return {"url": url, "ok": True, "kind": "page", "fingerprint": f"{title} | {h1} | {digest}".strip(" |"),
            "detail": "title | h1 | text hash"}


def main(argv: list[str]) -> int:
    timeout, budget = 20.0, 600.0
    args = argv[1:]
    for flag in ("--timeout", "--budget"):
        if flag in args:
            i = args.index(flag)
            if flag == "--timeout":
                timeout = float(args[i + 1])
            else:
                budget = float(args[i + 1])
            del args[i:i + 2]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    end = time.monotonic() + budget
    for url in args:
        left = end - time.monotonic()
        if left <= 0:
            r = {"url": url, "ok": False, "kind": None, "fingerprint": None, "partial": False, "final_url": url,
                 "detail": f"not checked: the {budget:g} s time budget ran out"}
        else:
            r = fingerprint(url, timeout, total=min(3 * timeout, left))
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
