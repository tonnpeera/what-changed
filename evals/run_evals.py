#!/usr/bin/env python3
"""Score a trial store. Every number is "passed / total".

Usage: python3 evals/run_evals.py evals/<case>.json [--offline]

A case file names a store and what a correct run must show:
  store                      path to the uptodate/ folder (relative to the repo)
  changelog                  {topic, url, baseline}: versions above `baseline` in the
                             live changelog are the ground truth for "detect the change"
  must_list_could_not_check  [url, ...] that must appear under "Could not check"
  rechecked_claims           {topic, ids}: seeded `unverified` claims a run should re-read
  no_change_run              {topic}: the latest run section must report this topic as "No change"
--offline skips the checks that need the network (quotes, changelog ground truth).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "what-changed" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from ledger import parse_ledger  # noqa: E402
from net import get  # noqa: E402

VERSION = re.compile(r"^##\s+v?(\d+(?:\.\d+)+)\s*$", re.M)


def vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def run_script(name: str, store: Path) -> tuple[int, int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPTS / name), str(store)], capture_output=True, text=True)
    m = re.search(r"(\d+)/(\d+)", proc.stdout)
    if proc.returncode not in (0, 1) or not m:
        return 0, 1, proc.stdout + proc.stderr  # a crash or no output is a failure, not 0/0
    return int(m.group(1)), int(m.group(2)), proc.stdout


def latest_digest(store: Path) -> str:
    files = sorted((store / "digests").glob("*.md"))
    return files[-1].read_text(encoding="utf-8") if files else ""


def section(text: str, heading: str) -> str:
    m = re.search(rf"^###\s+{re.escape(heading)}\s*$(.*?)(?=^###\s|^---|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else ""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case", help="a case file, e.g. evals/example-codex-run-2.json")
    ap.add_argument("--offline", action="store_true", help="skip the checks that need the network")
    args = ap.parse_args(argv[1:])
    offline = args.offline
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    store = ROOT / case["store"]
    rows: list[tuple[str, int, int, str]] = []

    p, t, _ = run_script("check_ledger.py", store)
    rows.append(("ledger format and confidence ceilings", p, t, "check_ledger.py"))

    if not offline:
        p, t, out = run_script("verify_quotes.py", store)
        unreachable = re.search(r"unreachable \(not counted\): (\d+)", out)
        rows.append(("quotes found verbatim on the cited page", p, t,
                     f"unreachable not counted: {unreachable.group(1) if unreachable else '?'}"))

    if "changelog" in case and not offline:
        c = case["changelog"]
        text, status = get(c["url"], timeout=60)
        versions = sorted({v for v in VERSION.findall(text or "") if vtuple(v) > vtuple(c["baseline"])}, key=vtuple)
        ledger_text = (store / "ledger" / f"{c['topic']}.md").read_text(encoding="utf-8")
        hit = [v for v in versions if v in ledger_text]
        rows.append(("new versions since baseline recorded in the ledger", len(hit), len(versions),
                     f"truth from live changelog ({status}): {', '.join(versions) or 'none'}"))

    digest = latest_digest(store)
    if case.get("must_list_could_not_check"):
        cnc = section(digest, "Could not check")
        urls = case["must_list_could_not_check"]
        hit = [u for u in urls if u in cnc]
        rows.append(("unreachable sources listed under Could not check", len(hit), len(urls), ""))

    if "rechecked_claims" in case:
        r = case["rechecked_claims"]
        claims = {c.id: c for c in parse_ledger(store / "ledger" / f"{r['topic']}.md").claims}
        ok = [i for i in r["ids"] if i in claims and
              (any(s.how == "read" for s in claims[i].sources) or claims[i].fields.get("status", "").startswith(("superseded", "retracted", "disputed")))]
        rows.append(("seeded unverified claims re-read or resolved", len(ok), len(r["ids"]),
                     f"not yet: {', '.join(i for i in r['ids'] if i not in ok) or 'none'}"))

    if "no_change_run" in case:
        topic = case["no_change_run"]["topic"]
        runs = re.split(r"^## Run ", digest, flags=re.M)
        last = runs[-1] if len(runs) > 1 else ""
        header = last.splitlines()[0] if last else ""
        quiet_form = "no change" in header.lower() and f"[{topic}]" in last  # template's quiet-day form
        full_form = topic in section(last, "No change")
        rows.append(("repeat run reports the unchanged topic as No change", int(quiet_form or full_form), 1,
                     "quiet-day form" if quiet_form else ""))

    rows = [(n, p, t if t else 1, note + (" (nothing to check counts as a fail)" if not t else "")) for n, p, t, note in rows]
    width = max(len(r[0]) for r in rows)
    total_p = sum(r[1] for r in rows)
    total_t = sum(r[2] for r in rows)
    print(f"eval {Path(argv[1]).stem}: {total_p}/{total_t} passed")
    for name, p, t, note in rows:
        print(f"  {p:>3}/{t:<3} {name.ljust(width)}  {note}")
    return 0 if total_p == total_t else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
