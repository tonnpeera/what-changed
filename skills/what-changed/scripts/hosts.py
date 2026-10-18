#!/usr/bin/env python3
"""Print every host a store's scripts may contact, one per line.

Usage: python3 hosts.py --store PATH [--topics FILE] [--comma | --allow EXTRA | --compare APPROVED]

Sandboxed agents (for example Claude Code's sandbox) refuse network access to hosts
that are not allowed; the scripts then report "blocked-local". Review this list, then
allow the hosts you trust. Reads only structured fields: topics.yaml sources, claim
source links and Source state URLs (never quotes or notes). IP addresses and local
names (localhost, numeric forms such as 0x7f.1) are never listed.

--allow EXTRA is for unattended runs: it prints two lines, the hosts the agent may
fetch (topics.yaml hosts plus EXTRA, comma-separated; "*.example.com" covers its
subdomains) and the matching Claude Code WebFetch(domain:...) rules. EXTRA "*" means
any host: the lines are then "*" and "WebFetch". An odd EXTRA entry exits 2.

--topics reads the watchlist from FILE instead of the store's topics.yaml (the schedulers pass the
copy you approved). --compare APPROVED compares the watchlist with an approved copy (a missing one
counts as empty): one summary line on stdout, and the added (+) and removed (-) sources on stderr.
Standard library only.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import urllib.parse
from pathlib import Path

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import NUMERIC_HOST  # noqa: E402

DNS_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def _host(url: str) -> str | None:
    """The URL's host if it is a plain DNS name. The output is pasted into allowlists, so IP
    addresses (an IPv6 literal fails DNS_NAME; dotted IPv4 and 0x7f.1 match NUMERIC_HOST) and
    *.localhost are dropped."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not DNS_NAME.match(host):
        return None
    if NUMERIC_HOST.match(host) or host.endswith(".localhost"):
        return None
    return host


def watchlist(store: Path, topics: Path | None = None) -> list[str]:
    """Hosts of the topics.yaml sources. Raises OSError or TopicsFormatError if it cannot be read."""
    from precheck import read_topics

    watch = {h for t in read_topics(topics or store / "topics.yaml") for u in t.get("sources", []) if (h := _host(u))}
    if "github.com" in watch:
        watch.add("raw.githubusercontent.com")  # release feeds and raw files
    return sorted(watch)


def compare(approved: Path, current: Path) -> tuple[str, list[str]]:
    """(summary, +/- lines) between an approved watchlist and the current one."""
    from precheck import read_topics

    def sources(path: Path) -> list[str]:
        if not path.exists():
            return []
        return [u for t in read_topics(path) for u in t.get("sources", [])]
    old, new = sources(approved), sources(current)
    added, removed = [u for u in new if u not in old], [u for u in old if u not in new]
    new_hosts = sorted({h for u in added if (h := _host(u))} - {h for u in old if (h := _host(u))})
    summary = (f"{len(added)} source(s) added, {len(removed)} removed; hosts not approved before: "
               f"{', '.join(new_hosts) or 'none'}")
    printable = lambda u: "".join(c if c.isprintable() else "?" for c in u)  # noqa: E731
    return summary, [f"+ {printable(u)}" for u in added] + [f"- {printable(u)}" for u in removed]


def hosts(store: Path) -> tuple[list[str], list[str]]:
    """Return (watchlist hosts, extra hosts seen only in ledgers). Structured fields only:
    topics.yaml `sources`, each claim's source links and Source state URLs. Free text
    (quotes, notes) is ignored, and anything that is not a plain DNS name is dropped.
    Ledgers are agent-written: a folder or an unreadable file among them is skipped."""
    from ledger import parse_ledger
    from precheck import SOURCE_STATE, TopicsFormatError

    try:
        watch = watchlist(store)
    except (OSError, TopicsFormatError):
        watch = []
    seen: set[str] = set()
    for f in sorted((store / "ledger").glob("*.md")):
        try:
            urls = [s.url for c in parse_ledger(f).claims for s in c.sources]
            urls += [m.group(1) for m in SOURCE_STATE.finditer(f.read_text(encoding="utf-8"))]
        except (OSError, UnicodeDecodeError):
            continue
        seen |= {h for u in urls if (h := _host(u))}
    return watch, sorted(seen - set(watch))


def allow_list(watch: list[str], extra: str) -> tuple[str, str]:
    """(hosts, WebFetch rules), both comma-separated, for --allow. Raises ValueError on an odd entry."""
    if extra.strip() == "*":
        return "*", "WebFetch"
    hosts_: list[str] = list(watch)
    for entry in (e.strip().lower().rstrip(".") for e in extra.split(",")):
        if not entry:
            continue
        name = entry[2:] if entry.startswith("*.") else entry
        if _host(f"https://{name}/") != name:
            raise ValueError(f"not a plain host name: {entry!r}")
        if entry not in hosts_:
            hosts_.append(entry)
    return ",".join(hosts_), ",".join(f"WebFetch(domain:{h})" for h in hosts_)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--comma", action="store_true", help="print only the watchlist hosts, as one comma-separated line")
    ap.add_argument("--allow", metavar="EXTRA", help="print the hosts an unattended run may fetch and the WebFetch rules")
    ap.add_argument("--topics", help="read the watchlist from this file instead of the store's topics.yaml")
    ap.add_argument("--compare", metavar="APPROVED", help="compare the watchlist with an approved copy")
    a = ap.parse_args(argv[1:])
    store = Path(a.store).expanduser()
    topics = Path(a.topics).expanduser() if a.topics else store / "topics.yaml"
    if a.compare is not None:
        from precheck import TopicsFormatError
        try:
            summary, lines = compare(Path(a.compare).expanduser(), topics)
        except (OSError, TopicsFormatError) as e:  # the detail can quote the file: stderr only
            print("could not compare the watchlists")
            print(f"hosts.py --compare: {e}", file=sys.stderr)
            return 2
        print(summary)
        if lines:
            print("\n".join(lines), file=sys.stderr)
        return 0
    if a.allow is not None:
        # Only topics.yaml counts here, never the agent-written ledgers. If it cannot be read, stop:
        # an empty list would refuse every fetch and the run would quietly do nothing.
        from precheck import TopicsFormatError
        try:
            print("\n".join(allow_list(watchlist(store, topics), a.allow)))
        except (OSError, TopicsFormatError) as e:
            print(f"hosts.py --allow: cannot read {topics} ({e})", file=sys.stderr)
            return 2
        except ValueError as e:
            print(f"hosts.py --allow: {e}", file=sys.stderr)
            return 2
        return 0
    watch, extra = hosts(store)
    if a.topics:
        from precheck import TopicsFormatError
        try:
            watch = watchlist(store, topics)
        except (OSError, TopicsFormatError):
            watch = []
    if a.comma:
        print(",".join(watch))
    else:
        print("# hosts in topics.yaml (needed for the daily check)")
        print("\n".join(watch))
    if extra and not a.comma:  # --comma output is meant to be pasted as-is
        print("# other hosts cited in the ledgers; review before allowing", file=sys.stderr)
        print("\n".join(extra), file=sys.stderr)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
