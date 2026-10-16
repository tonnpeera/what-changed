#!/usr/bin/env python3
"""Cheap "did this source change?" signal for one or more URLs.

Usage: python3 fingerprint.py URL [URL ...] [--timeout 20]
Prints one JSON object per URL:
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
from pathlib import Path

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import encode_url as net_encode, fetch  # noqa: E402

VERSION_HEADING = re.compile(r"^#{1,4}\s*\[?v?(\d+\.\d+(?:\.\d+)?[^\s\]]*)", re.M)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_HEADING = re.compile(rf"^#{{1,4}}\s*((?:{MONTHS}) \d{{1,2}}, \d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\s*$", re.M)


def first(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.S | re.I)
    return html.unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(1))).strip() if m else ""


def from_feed(text: str) -> tuple[str, str]:
    m = re.search(r"<(?:item|entry)\b(.*?)</(?:item|entry)>", text, re.S | re.I)
    item = m.group(1) if m else ""
    title = first(r"<title[^>]*>(.*?)</title>", item)
    when = first(r"<(?:updated|pubDate|published|dc:date)[^>]*>(.*?)</", item)
    if not item:
        return "(no items)", "feed has no entries"
    return f"{when} | {title}".strip(" |"), "newest item"


def fingerprint(url: str, timeout: float) -> dict:
    target = url
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/releases/?$", url)
    if m:
        target = f"https://github.com/{m.group(1)}/{m.group(2)}/releases.atom"
    r = fetch(target, timeout)
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
    title = first(r"<title[^>]*>(.*?)</title>", text)
    h1 = first(r"<h1[^>]*>(.*?)</h1>", text)
    body = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>|<[^>]+>", " ", text)
    digest = hashlib.sha256(re.sub(r"\s+", " ", body).encode()).hexdigest()[:12]
    return {"url": url, "ok": True, "kind": "page", "fingerprint": f"{title} | {h1} | {digest}".strip(" |"),
            "detail": "title | h1 | text hash"}


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
    for url in args:
        print(json.dumps(fingerprint(url, timeout), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
