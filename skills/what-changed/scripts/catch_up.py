#!/usr/bin/env python3
"""Session-start catch-up for what-changed.

If the store's runs.log has no run for today (local date), print a short note
that the host adds to the agent's context, so a missed scheduled run gets
picked up the next time you open a session. Prints nothing if today's run
already happened, or if the note was already shown today (so resuming a
session several times a day does not nag). If the scheduler (run-daily.sh / run-daily.ps1)
recorded why today's run did not finish, the note says so.

Usage:
  python3 catch_up.py --store PATH [--format plain|claude|codex|gemini|cursor|copilot]

Formats (what each host reads from a session-start hook's stdout):
  plain / claude / codex : plain text
  gemini, copilot        : {"hookSpecificOutput": {"additionalContext": ...}} / {"additionalContext": ...}
  cursor                 : {"additional_context": ...}

Set WHAT_CHANGED_AUTORUN=1 to ask the agent to run immediately instead of offering.
Standard library only. Never fails the session: any error exits 0 silently.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import date, datetime, time
from pathlib import Path

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")


def is_daily_run(line: str) -> bool:
    """A run that covered every due topic. Runs of named topics (scope=topics) and
    hand seeding do not count. Older lines without scope= count if due=x/x."""
    if not line.strip() or "mode=manual-seed" in line:
        return False
    fields = dict(f.split("=", 1) for f in line.split("\t")[1:] if "=" in f)
    if "scope" in fields:
        return fields["scope"] == "all"
    done, _, total = fields.get("due", "").partition("/")
    return bool(done) and done == total


def daily_run_dates(runs_log: Path) -> list[str]:
    if not runs_log.is_file():
        return []
    return [line[:10] for line in runs_log.read_text(encoding="utf-8", errors="replace").splitlines() if is_daily_run(line)]


def written_since(path: Path, day: str) -> bool:
    """True if the file was last written on or after local midnight starting `day`."""
    midnight = datetime.combine(date.fromisoformat(day), time.min).timestamp()  # local time
    return path.stat().st_mtime >= midnight


def ran_today(runs_log: Path, today: str) -> bool:
    """True if runs.log has an all-topics run dated today and the file was written today.
    The agent writes runs.log, so it could log future days as done; a line dated today in a
    file last written before today was written in advance and does not count. Any write today
    makes such a line count again, so this only decides whether to *offer* a run (catch-up hook)
    or to skip a duplicate quiet-day note; schedulers do not skip runs on it."""
    return today in daily_run_dates(runs_log) and written_since(runs_log, today)


TOPICS_APPROVAL = "topics.yaml needs your approval"  # how the schedulers start that reason
APPROVED_SINCE = "it stopped for topics.yaml, which has been approved since"  # the line an approval adds


def state_base(store: Path) -> Path:
    """Where the schedulers keep this project's state: outside the project, under a key made from
    the project folder (the store's parent). Add ".topics.yaml" for the approved copy, or "/" for logs."""
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "what-changed"
    return state / hashlib.sha256(str(store.resolve().parent).encode()).hexdigest()[:16]


def error_file(store: Path, today: str) -> Path:
    return state_base(store) / f"{today}-error.txt"


def scheduler_error(store: Path, today: str) -> str | None:
    """The last reason the scheduler gave today for not finishing, if any. Kept short, except a
    stop for topics.yaml, whose approval command comes near its end."""
    path = error_file(store, today)
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8-sig", errors="replace").strip().splitlines()  # PowerShell 5.1 adds a BOM
    if not lines:
        return None
    text = lines[-1].split(" did not finish: ", 1)[-1]
    return text[:1000 if text.startswith(TOPICS_APPROVAL) else 400]


def scheduler_used(store: Path) -> bool:
    """A scheduler has started for this project, or its approve step ran (both make this folder)."""
    return state_base(store).is_dir()


def topics_hash(store: Path) -> str | None:
    """The 32 hash characters that name the current topics.yaml in the schedulers' approve step."""
    try:
        return hashlib.sha256((store / "topics.yaml").read_bytes()).hexdigest()[:32]
    except OSError:
        return None


def topics_approved(store: Path) -> bool | None:
    """Whether topics.yaml is the copy approved for scheduled runs (None: there is no approved copy,
    or topics.yaml cannot be read)."""
    approved = state_base(store).with_name(state_base(store).name + ".topics.yaml")
    try:
        return approved.read_bytes() == (store / "topics.yaml").read_bytes()
    except OSError:
        return None


def message(store: Path, last: str | None, autorun: bool, error: str | None = None,
            approved: bool | None = None, full_text: Path | None = None,
            scheduler: bool = False, version: str | None = None) -> str:
    when = f"last run {last}" if last else "no run recorded yet"
    stopped = bool(error and error.startswith(TOPICS_APPROVAL))
    if stopped and approved:
        error, stopped = APPROVED_SINCE + "; today's run can start again", False
    if approved is False and error and error.startswith(APPROVED_SINCE):
        error = None  # changed again after that approval
    if error:
        when += f"; the scheduled run reported: {error}"
    first = approved is None and scheduler and not stopped and version is not None
    if approved is False and not stopped:
        when += "; topics.yaml changed since it was approved for scheduled runs"
    if first:
        when += "; topics.yaml has not been approved for scheduled runs yet"
    if stopped or approved is False or first:
        # Its sources may come from an agent: no run, until the user has looked at them.
        where = f" (the full message is in {full_text})" if stopped and full_text else ""
        if not stopped and version:
            where = (f": the scheduler's approve step with WHAT_CHANGED_APPROVE_TOPICS={version} "
                     f"(Windows: -ApproveTopics {version}), set up like its timer")
        action = ("At the start of your first reply, tell the user in one line that the daily run is stopped until "
                  "they review topics.yaml and approve it with the scheduler's command" + where + " (running the "
                  "scheduler by hand also prints it). Do not run what-changed, do not run that command yourself "
                  "and do not open the files it names: the approval has to come from the user.")
    elif autorun:
        action = ("Before anything else, use the what-changed skill to run all due topics "
                  "in light mode, then tell the user the digest's top section in two lines.")
    else:
        action = ("At the start of your first reply, tell the user in one line and offer to run it now "
                  "(\"Use the what-changed skill: run all due topics in light mode\"). "
                  "Do not run it without their yes.")
    return f"what-changed: today's update has not run ({when}; store: {store}). {action}"


def render(text: str, fmt: str) -> str:
    if fmt == "gemini":
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})
    if fmt == "copilot":
        return json.dumps({"additionalContext": text})
    if fmt == "cursor":
        return json.dumps({"additional_context": text})
    return text  # plain, claude, codex


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--format", default="plain",
                    choices=["plain", "claude", "codex", "gemini", "cursor", "copilot"])
    args = ap.parse_args()
    store = Path(os.path.expanduser(args.store))
    today = date.today().isoformat()

    dates = daily_run_dates(store / "runs.log")
    if ran_today(store / "runs.log", today):
        return 0
    dates = [d for d in dates if d < today]
    last = max(dates) if dates else None
    marker = store / ".catchup-notified"
    if marker.is_file() and not marker.is_symlink() and marker.read_text(encoding="utf-8", errors="replace").strip() == today:
        return 0
    if not store.is_dir():
        return 0
    try:
        error = scheduler_error(store, today)
    except OSError:
        error = None
    autorun = os.environ.get("WHAT_CHANGED_AUTORUN") == "1"
    print(render(message(store, last, autorun, error, topics_approved(store), error_file(store, today),
                         scheduler_used(store), topics_hash(store)), args.format))
    # The hook runs outside any sandbox: never write through a link an agent planted in the store.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from ledger import open_in_store
        with open_in_store(store, marker, append=False) as f:
            f.write(today)
    except Exception:  # never fail or hang the session over the reminder marker
        pass
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
