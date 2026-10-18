#!/usr/bin/env python3
"""Decide, without a model, whether today's run needs an agent at all.

Usage: python3 precheck.py --store PATH [--today YYYY-MM-DD] [--timeout 20]

For every topic in topics.yaml it works out whether the topic is due (cadence,
claims past review_by, low/disputed claims to re-check) and, for due topics,
fingerprints the sources and compares them with the ledger's Source state.

Exit codes:
  0   nothing needs an agent. A quiet-day section was appended to today's digest,
      the ledgers' last_run / checked dates were updated, and runs.log got a
      scope=all line (tokens=0). Also 0, writing nothing, if nothing needed checking
      because the topics ran earlier today or today's all-topics run is logged.

runs.log and the ledgers are written by the agent, so they are trusted only as far as
file dates allow: a ledger whose last_run is today counts as done only if the file was
written today, and a last_run after today needs the agent.
  10  an agent is needed; the reasons are printed, one topic per line. Nothing written.
  11  could not check: no due topic could be checked, because none of their sources could be
      fetched (timeout, error, blocked by a local proxy or sandbox). A "Could not check"
      section is appended to today's digest, but no topic is marked as checked and no scope=all
      line is written, so the day does not count as done: the next run tries again.
      If some due topics were checked and others could not be, the exit code is 0: the digest
      section says which topics could not be checked, those keep their last_run (so they are
      due again next time), and a source that has failed 3 runs in a row is marked "possibly
      gone" (the counter is kept in the ledger's Source state).
  2   usage error, or topics.yaml is not in the simple format this script reads
      (then just run the agent).

Reads the simple YAML used by assets/topics.example.yaml (no anchors, no multi-line
strings). Standard library only.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catch_up import daily_run_dates, ran_today, written_since  # noqa: E402
from fingerprint import fingerprint  # noqa: E402
from ledger import UnsafeWrite, open_in_store, parse_ledger, unsafe_target  # noqa: E402

CADENCE_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}
SOURCE_STATE = re.compile(r'^- (\S+)(?: (?:→|->) \S+)? — fingerprint: "?(.*?)"? — checked: (\S+)', re.M)
NEEDS_AGENT = 10
COULD_NOT_CHECK = 11
TOPIC_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
STATE_LINE = re.compile(r'^(- (\S+)(?: (?:→|->) \S+)? — fingerprint: .*? — checked: )(\S+)(.*)$', re.M)
FAILED_IN_A_ROW = re.compile(r"— failed \((\d+) in a row\)")
CONTROL = re.compile(r"[\x00-\x1f\x7f\x85\u2028\u2029]+")  # page-made text must stay on its digest line
POSSIBLY_GONE = 3


class TopicsFormatError(Exception):
    pass


def read_topics(path: Path) -> list[dict]:
    """Parse the simple topics.yaml format (a list of flat mappings with one list field)."""
    topics: list[dict] = []
    current: dict | None = None
    list_key: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.strip().startswith("#") or line.strip() == "topics:":
            continue
        m = re.match(r"^\s*- id:\s*(\S+)$", line)
        if m:
            if not TOPIC_ID.match(m.group(1)):
                raise TopicsFormatError(f"topic id must be lowercase letters, digits, - or _: {m.group(1)!r}")
            current = {"id": m.group(1), "sources": []}
            topics.append(current)
            list_key = None
            continue
        if current is None:
            raise TopicsFormatError(f"unexpected line before first topic: {raw!r}")
        m = re.match(r"^\s+- (\S+)$", line)
        if m and list_key:
            current[list_key].append(m.group(1))
            continue
        m = re.match(r"^\s+([a-z_]+):\s*(.*)$", line)
        if not m:
            raise TopicsFormatError(f"cannot read line: {raw!r}")
        key, value = m.group(1), m.group(2).strip().strip('"')
        if value == "":
            list_key = key
            current.setdefault(key, [])
        else:
            list_key = None
            current[key] = value
    if not topics:
        raise TopicsFormatError("no topics found")
    return topics


def comparable(fp: str | None, kind: str | None) -> str | None:
    """The meaningful part of a fingerprint: the tag for release feeds, the hash for pages."""
    if fp is None:
        return None
    fp = fp.strip().strip('"')
    if kind == "release-feed" or (kind is None and "|" in fp and re.search(r"\bv?\d+\.\d+", fp.split("|")[-1])):
        return fp.split("|")[-1].strip().lstrip("v")
    if kind == "page" or (kind is None and fp.count("|") >= 2):
        return fp.split("|")[-1].strip()
    return fp.lstrip("v")


def made_by_script(fp: str, kind: str | None) -> bool:
    """Whether a stored fingerprint has the shape fingerprint.py gives this kind of source. An
    agent that could not run the script may have written its own (a date, a sentence)."""
    fp = fp.strip().strip('"')
    if kind == "page":
        return bool(re.search(r"(?:^|\| )[0-9a-f]{12}$", fp))
    if kind in ("feed", "release-feed"):
        return "|" in fp
    if kind == "changelog":
        return "|" not in fp and len(fp) <= 40
    return True


def ledger_path_for(store: Path, topic_id: str) -> Path:
    """The ledger file for a topic, refusing anything that would leave store/ledger/."""
    if not TOPIC_ID.match(topic_id):
        raise TopicsFormatError(f"unsafe topic id {topic_id!r}")
    why = unsafe_target(store, store / "ledger" / f"{topic_id}.md")
    if why:
        raise TopicsFormatError(f"ledger for {topic_id!r}: {why}")
    base = (store / "ledger").resolve()
    path = (base / f"{topic_id}.md").resolve()
    if path.parent != base:
        raise TopicsFormatError(f"unsafe topic id {topic_id!r}")
    return path


def topic_status(topic: dict, store: Path, today: date, timeout: float) -> tuple[str, str, dict]:
    """Return (state, reason, details). state: ran-today | not-due | quiet | unchecked | agent."""
    ledger_path = ledger_path_for(store, topic["id"])
    if not ledger_path.is_file():
        return "agent", "never run (no ledger yet)", {}
    ledger = parse_ledger(ledger_path)
    last_run = ledger.frontmatter.get("last_run", "")
    try:
        last = date.fromisoformat(last_run)
    except ValueError:
        return "agent", f"ledger has no valid last_run ({last_run!r})", {}
    if last > today:  # written in advance, which would skip the topic until then
        return "agent", f"ledger last_run {last_run} is after today", {}
    if last == today:
        if not written_since(ledger_path, today.isoformat()):
            return "agent", "ledger says it ran today but was last written before today", {}
        # A run today already covered this topic; its digest section is the day's result.
        return "ran-today", f"ran earlier today ({last_run})", {}

    cadence = CADENCE_DAYS.get(topic.get("cadence", "daily"), 1)
    next_due = last + timedelta(days=cadence)
    cadence_due = today >= next_due
    due_claims = []
    for c in ledger.claims:
        status = (c.fields.get("status", "").split() or [""])[0]
        if status in ("superseded", "retracted"):
            continue
        rb = c.dates.get("review_by")
        if rb and rb <= today.isoformat():
            due_claims.append(f"{c.id} review_by {rb}")
        level = (c.fields.get("confidence", "").split("—")[0].split() or [""])[0]
        # Weak claims are re-checked on the topic's own schedule, not every day.
        if cadence_due and topic.get("recheck_low", "false") == "true" and (level in ("low", "very-low") or status == "disputed"):
            due_claims.append(f"{c.id} is {status if status == 'disputed' else level}")
    if due_claims:
        return "agent", "claims due: " + ", ".join(due_claims[:5]), {}

    if not cadence_due:
        return "not-due", f"next: {next_due.isoformat()}", {}

    stored = {m.group(1): m.group(2) for m in SOURCE_STATE.finditer(ledger_path.read_text(encoding="utf-8", errors="replace"))}
    lines, failed = [], []
    for url in topic.get("sources", []):
        try:
            r = fingerprint(url, timeout)
        except Exception as e:  # one page's content must not stop the other topics
            failed.append((url, f"fingerprint error: {type(e).__name__}"))
            continue
        if not r["ok"]:
            failed.append((url, r["detail"]))
            continue
        if r["kind"] == "page" and r.get("partial"):
            r = fingerprint(url, timeout)
            if r.get("partial"):
                failed.append((url, "download truncated (page hash not comparable)"))
                continue
        old = stored.get(url)
        if old is None or old.strip().startswith("(none") or old.strip() in ("", "unavailable"):
            return "agent", f"no stored fingerprint for {url}", {}
        if not made_by_script(old, r["kind"]):
            return "agent", (f"stored fingerprint for {url} was not made by fingerprint.py ({old!r}); "
                             "a new baseline is needed"), {}
        if comparable(old, None) != comparable(r["fingerprint"], r["kind"]):
            return "agent", f"source changed: {url}: {old} → {r['fingerprint']}", {}
        lines.append(f"{url} → {CONTROL.sub(' ', r['fingerprint'])}")
    if failed and not lines:  # nothing was compared: that is "could not check", never "no change"
        return "unchecked", "could not check any source", {"failed": failed}
    return "quiet", "fingerprints unchanged", {"lines": lines, "failed": failed, "next": today + timedelta(days=cadence)}


def touch_ledger(store: Path, path: Path, today: str, ok_urls: set[str], failed: dict[str, str],
                 checked: bool) -> dict[str, int]:
    """Update Source state: date and "ok" for sources that answered, a failures-in-a-row counter
    for those that did not. last_run moves only for a topic that was checked. Returns the
    counters of the failed sources."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if checked:
        text = re.sub(r"^last_run: .*$", f"last_run: {today}", text, count=1, flags=re.M)
    counts: dict[str, int] = {}

    def update(m: re.Match) -> str:
        head, url, tail = m.group(1), m.group(2), m.group(4)
        if url in ok_urls:
            return head + today + (" — ok" if "— failed" in tail else tail)
        if url in failed:
            before = FAILED_IN_A_ROW.search(tail)
            counts[url] = (int(before.group(1)) if before else 0) + 1
            return head + m.group(3) + f" — failed ({counts[url]} in a row): {failed[url]}"
        return m.group(0)
    text = STATE_LINE.sub(update, text)
    with open_in_store(store, path, append=False) as f:
        f.write(text)
    return counts


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--list-sources", action="store_true", help="print every source URL in topics.yaml and exit")
    args = ap.parse_args(argv[1:])
    store = Path(args.store).expanduser().absolute()
    today = date.fromisoformat(args.today)
    if args.list_sources:
        try:
            for t in read_topics(store / "topics.yaml"):
                for url in t.get("sources", []):
                    print(url)
        except (OSError, TopicsFormatError) as e:
            print(f"precheck: cannot read topics.yaml ({e})")
            return 2
        return 0

    future = sorted({d for d in daily_run_dates(store / "runs.log") if d > today.isoformat()})
    if future:
        print(f"note: runs.log has runs dated after today ({', '.join(future[:3])}); they will not count")
    try:
        topics = read_topics(store / "topics.yaml")
    except (OSError, TopicsFormatError) as e:
        print(f"precheck: cannot read topics.yaml ({e}); run the agent instead")
        return 2

    try:
        results = [(t, *topic_status(t, store, today, args.timeout)) for t in topics]
    except TopicsFormatError as e:  # e.g. a ledger that is a symlink out of ledger/
        print(f"precheck: {e}; run the agent instead")
        return 2
    blocked = [f for _, state, _, d in results if state in ("quiet", "unchecked")
               for f in d.get("failed", []) if "blocked-local" in f[1]]
    if blocked:
        print(f"note: {len(blocked)} source(s) were blocked by a local proxy or sandbox, not by the sites. "
              f"Allow the hosts listed by: python3 {Path(__file__).parent / 'hosts.py'} --store {store}")
    agent = [(t["id"], reason) for t, state, reason, _ in results if state == "agent"]
    if agent:
        for tid, reason in agent:
            print(f"needs agent: [{tid}] {reason}")
        for t, state, reason, _ in results:
            if state in ("not-due", "ran-today"):
                print(f"not due: [{t['id']}] ({reason})")
            elif state == "unchecked":
                print(f"could not check: [{t['id']}] no source could be fetched")
        return NEEDS_AGENT
    ran = [t["id"] for t, state, _, _ in results if state == "ran-today"]
    if not any(state in ("quiet", "unchecked") for _, state, _, _ in results):
        # Nothing was checked: a "No change" section and a scope=all line would misstate today.
        if ran:
            print(f"nothing to check: [{'], ['.join(ran)}] ran earlier today; nothing else is due. Wrote nothing.")
            return 0
        if ran_today(store / "runs.log", today.isoformat()):
            print(f"already ran today ({today}); nothing is due. Wrote nothing.")
            return 0

    now = datetime.now().astimezone()
    started = now.replace(year=today.year, month=today.month, day=today.day)  # honours --today
    quiet = [(t, d) for t, state, _, d in results if state == "quiet"]
    unchecked = [(t, d) for t, state, _, d in results if state == "unchecked"]
    not_due = [(t, reason) for t, state, reason, _ in results if state in ("not-due", "ran-today")]
    if unchecked and not quiet:
        title = "Could not check"
    elif unchecked:
        title = f"No change in {len(quiet)} topic(s); could not check {len(unchecked)}"
    else:
        title = "No change"
    due = len(quiet) + len(unchecked)
    digest = store / "digests" / f"{today}.md"
    ledgers = [store / "ledger" / f"{t['id']}.md" for t, _ in quiet + unchecked]
    # Check every file first, so a refusal leaves nothing half-written; open_in_store checks again.
    for target in [digest, store / "runs.log", *ledgers]:
        why = unsafe_target(store, target)
        if why:
            print(f"precheck: refusing to write: {why} (a symlink or hard link); run the agent instead")
            return 2
    try:
        counts: dict[str, int] = {}
        for (t, d), path in zip(quiet + unchecked, ledgers):
            ok = {line.split(" → ")[0] for line in d.get("lines", [])}
            counts.update(touch_ledger(store, path, today.isoformat(), ok, dict(d["failed"]), checked=(t, d) in quiet))
    except UnsafeWrite as e:
        print(f"precheck: refusing to write: {e}; run the agent instead")
        return 2
    section = [f"## Run {started:%H:%M} (precheck script, no agent) — {title}"]
    could_not = []
    for t, d in unchecked:
        section.append(f"- [{t['id']}] could not check any source; not counted as checked, the next run tries again")
    for t, d in quiet:
        section.append(f"- [{t['id']}] fingerprints unchanged: " + "; ".join(d["lines"]) + f"; next due: {d['next']}")
    for t, d in unchecked + quiet:
        for url, detail in d["failed"]:
            gone = " — possibly gone: consider replacing or removing it" if counts.get(url, 0) >= POSSIBLY_GONE else ""
            could_not.append(f"- [{t['id']}] {url} — {CONTROL.sub(' ', detail)} (failed {counts.get(url, 1)} run(s) in a row){gone}")
    section += [f"- not due: [{t['id']}] ({reason})" for t, reason in not_due]
    if could_not:
        section += ["", "### Could not check"] + could_not
    section += ["", f"Run stats: topics due {due}/{len(topics)} · topics checked {len(quiet)}/{due} · "
                    "pages read 0 · searches 0 · tokens: 0 (no model)", ""]

    try:
        prefix = "" if digest.exists() else f"# Digest {today}\n\n"
        with open_in_store(store, digest, append=True) as f:
            f.write(prefix + "\n".join(section) + "\n")
        # A day on which no due topic could be checked is not done: scope=topics does not count for
        # schedulers and hooks. Once any topic was checked, the day is done; the others stay due.
        with open_in_store(store, store / "runs.log", append=True) as f:
            f.write("\t".join([
                started.isoformat(timespec="seconds"), "scope=topics" if unchecked and not quiet else "scope=all",
                "mode=precheck", "host=precheck-script",
                f"due={due}/{len(topics)}", "checked=" + (",".join(t["id"] for t, _ in quiet) or "none"),
                "changed=0", "new=0", "superseded=0", f"could_not_check={len(could_not)}",
                "pages=0", "searches=0", "tokens=0"]) + "\n")
    except UnsafeWrite as e:
        print(f"precheck: refusing to write: {e}; run the agent instead")
        return 2
    if unchecked and not quiet:
        print(f"could not check: [{'], ['.join(t['id'] for t, _ in unchecked)}] no source could be fetched; "
              f"today is not counted as done; wrote {digest}")
        return COULD_NOT_CHECK
    extra = f", could not check {len(unchecked)} (see the digest)" if unchecked else ""
    print(f"quiet day: {len(quiet)} topic(s) unchanged{extra}, {len(not_due)} not due; wrote {digest}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
