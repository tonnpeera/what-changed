#!/usr/bin/env python3
"""Read the run's time from the system clock and append the runs.log line.

A model's own sense of the time is often wrong, so the times in runs.log and in the
digest's "## Run HH:MM" heading come from this script, not from the agent.

Usage:
  python3 log_run.py --now
      Print the current local time: an ISO timestamp with offset on the first line,
      HH:MM on the second. Use it at the start of a run; writes nothing.
  python3 log_run.py --store PATH [--started ISO] scope=all|topics FIELD=VALUE ...
      Append one tab-separated line to PATH/runs.log: the timestamp, then the fields
      in the order given (see references/ledger-format.md). The timestamp is --started
      (the value --now printed when the run began) if it is today and not in the
      future, else the current time. Prints the line it wrote.

Exit code 2 on a usage error or a refused write. Standard library only; no network.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger import UnsafeWrite, open_in_store, outside_store  # noqa: E402

FIELD = re.compile(r"[a-z_]+=[^\t\r\n]*")  # used with fullmatch: no tab or line break anywhere
MAX_RUN_LENGTH = timedelta(hours=12)


def now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def run_start(started: str | None, clock: datetime) -> tuple[datetime, str | None]:
    """The timestamp for the line, and why --started was not used (None if it was)."""
    if not started:
        return clock, None
    try:
        value = datetime.fromisoformat(started)
    except ValueError:
        return clock, f"--started {started!r} is not an ISO timestamp"
    value = value.astimezone(clock.tzinfo)  # compare days in local time, whatever offset was given
    if value > clock + timedelta(seconds=60):
        return clock, f"--started {started} is in the future"
    if value.date() != clock.date() or clock - value > MAX_RUN_LENGTH:
        return clock, f"--started {started} is not from this run"
    return value, None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--now", action="store_true")
    ap.add_argument("--store")
    ap.add_argument("--started")
    ap.add_argument("fields", nargs="*")
    args = ap.parse_args(argv[1:])
    clock = now()
    if args.now:
        print(clock.isoformat())
        print(f"{clock:%H:%M}")
        return 0
    if not args.store:
        print("log_run: --store is required unless --now is given")
        return 2
    bad = [f for f in args.fields if not FIELD.fullmatch(f)]
    if bad:
        print(f"log_run: fields must look like name=value, without tabs or line breaks: {bad}")
        return 2
    if not any(f in ("scope=all", "scope=topics") for f in args.fields):
        print("log_run: give scope=all (all due topics) or scope=topics (named topics)")
        return 2
    store = Path(args.store).expanduser().absolute()
    refused = outside_store(store)
    if refused:
        print(f"log_run: refused: {args.store} is outside the store ({refused})")
        return 2
    if not (store / "topics.yaml").is_file():
        print(f"log_run: {store} has no topics.yaml; is it the store?")
        return 2
    stamp, why = run_start(args.started, clock)
    if why:
        print(f"log_run: note: {why}; using the current time")
    line = "\t".join([stamp.isoformat(timespec="seconds"), *args.fields])
    try:
        with open_in_store(store, store / "runs.log", append=True) as f:
            f.write(line + "\n")
    except UnsafeWrite as e:
        print(f"log_run: refusing to write: {e}")
        return 2
    print(line)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
