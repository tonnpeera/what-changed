#!/usr/bin/env bash
# Run what-changed once, unattended, with a headless agent CLI.
# Schedule it with cron or launchd (see ../README.md).
#
#   WHAT_CHANGED_HOST=claude|antigravity|codex|qwen   which CLI to use (required)
#   WHAT_CHANGED_PROJECT=/path/to/project         folder that holds uptodate/ and has the skill installed
#   WHAT_CHANGED_FETCH_DOMAINS=a.org,*.b.com      claude host: hosts the agent may fetch besides the ones
#                                                 in topics.yaml (optional; "*" = any host)
#   WHAT_CHANGED_CLAUDE=/path/to/claude           claude host: which claude to run (optional; default:
#                                                 ~/.local/bin/claude, where the installer puts it, else PATH)
#   WHAT_CHANGED_VERSION_TIMEOUT=30               claude host: seconds `claude --version` may take (optional)
#   WHAT_CHANGED_APPROVE_TOPICS=<32 characters>   approve the topics.yaml you reviewed, then exit (runs stop
#                                                 while topics.yaml differs from the approved copy; the stop
#                                                 message shows what changed and the exact command)
#
# Exits early once it has completed a run today (its own record under ~/.local/state/what-changed/,
# outside the project, where no host's agent writes), so it is safe to schedule more than once a day.
# It does not trust runs.log for that: the agent writes runs.log. Topics an interactive run already covered today are
# skipped by precheck (0 tokens). cron and launchd start with a minimal PATH, which usually lacks
# ~/.local/bin (where Claude Code's installer puts `claude`), so that is looked at first.
# After the agent, it checks that today's run is in runs.log; if the agent wrote today's digest but
# no log line, it adds one (marked logged_by=scheduler); if there is no digest, the day stays open.
#
# When it cannot run (a refused setup, claude missing, too old or not answering, no due topic
# reachable, the agent failing) it says why on stderr, writes the reason to
# <state dir>/<today>-error.txt, which the catch-up hook shows in your next session, and does not
# count the day as done.
#
# No Gemini CLI option: its tool permissions could not be narrowed enough for unattended runs.
# Unattended runs read untrusted web pages. Tool access is kept narrow on purpose (claude host):
# reads only uptodate/ and the skill, writes only the ledgers and digests (runs.log only through
# log_run.py), fetches only allowed hosts, no general shell, only four of the skill's scripts, no curl.
# Other hosts: use their own sandbox/approval settings to get the same effect.
set -euo pipefail

HOST="${WHAT_CHANGED_HOST:?set WHAT_CHANGED_HOST to claude, antigravity, codex or qwen}"
CLAUDE_MIN="2.1.248"   # --restricted
PROJECT="${WHAT_CHANGED_PROJECT:?set WHAT_CHANGED_PROJECT to the folder that contains uptodate/}"
PROJECT="$(cd "$PROJECT" && pwd)"   # absolute, so later cd's do not change what it means
SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
STORE="$PROJECT/uptodate"
TODAY="$(date +%Y-%m-%d)"
# Code here runs outside any agent sandbox, so it must not load anything the agent can write.
# Python runs with -I (isolated mode), which keeps the current folder off the import path; without
# it a json.py or pathlib.py dropped in $PROJECT would run as you.

# Only the claude host limits the agent's writes to uptodate/. The other hosts can write anywhere in
# the project, so a skill installed inside it (.agents/skills, .qwen/skills, ...) could be rewritten
# by a prompt-injected agent and then run by this script, outside the sandbox, on the next day.
REAL_PROJECT="$(cd "$PROJECT" && pwd -P)"
REAL_SKILL="$(cd "$SKILL_DIR" && pwd -P)"
# Logs, the reason a run did not finish and the date of the last completed run live outside the
# project: hosts other than claude can write anywhere in it, so a planted marker could skip runs and
# a planted symlink (a log file -> ~/.zshrc) would make this script write into that file.
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/what-changed"
# The same key catch_up.py computes, made without Python, so even "no suitable Python" can be recorded.
if command -v sha256sum >/dev/null; then SHA="sha256sum"; else SHA="shasum -a 256"; fi
KEY="$(printf '%s' "$REAL_PROJECT" | $SHA | cut -c1-16)"
DONE="$STATE_DIR/$KEY.last-run"
LOGDIR="$STATE_DIR/$KEY"
mkdir -p "$LOGDIR"
OUT="$LOGDIR/$TODAY-$HOST.out"
ERR="$LOGDIR/$TODAY-$HOST.err"
ERROR_FILE="$LOGDIR/$TODAY-error.txt"
fail() {  # reason, exit code: say it where a person will see it, and leave the day not done
  echo "what-changed: $1" >&2
  printf '%s what-changed scheduled run did not finish: %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$1" >> "$ERROR_FILE"
  exit "$2"
}
case "$REAL_SKILL/" in
  "$REAL_PROJECT/uptodate/"*)
    fail "refusing: the skill folder is inside uptodate/, which the agent can edit; install it elsewhere" 2 ;;
  "$REAL_PROJECT/"*)
    if [ "$HOST" != claude ]; then
      fail "refusing: host $HOST can write anywhere in $PROJECT, and the skill is installed inside it ($SKILL_DIR). Install the skill outside the project (e.g. ~/.agents/skills/what-changed) for unattended runs." 2
    fi ;;
esac
case "$HOST" in claude) ;; *)
  if [ -L "$STORE" ]; then fail "refusing: $STORE is a symlink, and host $HOST can create those" 2; fi ;;
esac
# The approved copy of topics.yaml lives in the state folder too, so it must be out of the agent's reach.
REAL_STATE="$(cd "$STATE_DIR" && pwd -P)"
case "$REAL_STATE/" in "$REAL_PROJECT/"*)
  if [ "$HOST" != claude ]; then
    fail "refusing: the state folder $REAL_STATE is inside $PROJECT, where host $HOST can write. Set XDG_STATE_HOME to a folder outside it." 2
  fi ;;
esac
# Python 3.11 or later. cron and launchd start with a minimal PATH, where python3 may be the 3.9 from
# Apple's command line tools; WHAT_CHANGED_PYTHON picks one, otherwise the first new enough of these.
py_ok() { [ -n "$1" ] && "$1" -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; }
PY="${WHAT_CHANGED_PYTHON:-}"
if [ -n "$PY" ]; then
  py_ok "$PY" || fail "WHAT_CHANGED_PYTHON=$PY is not Python 3.11 or later" 2
else
  for candidate in python3 python3.15 python3.14 python3.13 python3.12 python3.11 \
                   "$HOME/.local/bin/python3" /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    found="$(command -v "$candidate" 2>/dev/null || true)"
    if py_ok "$found"; then PY="$found"; break; fi
  done
  if [ -z "$PY" ]; then
    fail "no Python 3.11 or later found (PATH=$PATH). Install one from python.org or Homebrew (the python3 from Apple's command line tools can be 3.9), or set WHAT_CHANGED_PYTHON to its full path" 2
  fi
fi
# claude needs USER to find its login; cron and launchd may not set it.
USER="${USER:-$(id -un)}"
export USER
REAL_STORE="$(cd "$STORE" 2>/dev/null && pwd -P)" || fail "no store folder at $STORE" 2
PROMPT="Use the what-changed skill: run all due topics in light mode. Store: $REAL_STORE. The skill's instructions: $REAL_SKILL/SKILL.md."

# Why the agent CLI failed (its JSON result in $OUT, else the end of $ERR), for the person reading
# stderr only: the text can come from the model, so it never goes into the error file, which the
# catch-up hook puts into the next session's context.
agent_error() {
  "$PY" -I - "$OUT" "$ERR" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        result = json.load(f).get("result")
except (OSError, ValueError, AttributeError):
    result = None
if not result:
    try:
        with open(sys.argv[2], encoding="utf-8", errors="replace") as f:
            result = " ".join(f.read().split()[-40:])
    except OSError:
        result = ""
print("what-changed: claude said: " + " ".join(str(result or "no message").split())[:300])
PY
}

cd "$PROJECT"

# topics.yaml decides which hosts precheck fetches and which ones the claude agent may fetch, and
# other hosts' agents (or an interactive session) can edit it. So the scheduled steps never read it:
# precheck and hosts.py read a copy you approved, kept here outside the project. A run stops while
# topics.yaml differs from that copy, and a run whose agent changed it is not counted as done.
TOPICS="$STORE/topics.yaml"
APPROVED="$STATE_DIR/$KEY.topics.yaml"
sha_of() { $SHA < "$1" | cut -d' ' -f1; }
read_topics_hash() {
  [ -f "$TOPICS" ] || fail "there is no topics.yaml file in $STORE; add a topic first" 2
  TOPICS_HASH="$(sha_of "$TOPICS")" || fail "cannot read $TOPICS" 7
}
approve() {  # copy topics.yaml as the approved version, if it still is the one with hash $TOPICS_HASH
  cp "$TOPICS" "$APPROVED.new" && [ "$(sha_of "$APPROVED.new")" = "$TOPICS_HASH" ] && mv "$APPROVED.new" "$APPROVED" \
    || { rm -f "$APPROVED.new"; fail "could not record the approval of $TOPICS (did it change just now?)" 7; }
  echo "approved topics.yaml ${TOPICS_HASH:0:32}; scheduled runs fetch only from: $("$PY" -I "$SKILL_DIR/scripts/hosts.py" --store "$STORE" --topics "$APPROVED" --comma)"
}
topics_stop() {  # why: show what changed against the approved copy, then stop with the command that approves it
  CMD="WHAT_CHANGED_APPROVE_TOPICS=${TOPICS_HASH:0:32} WHAT_CHANGED_HOST=$HOST WHAT_CHANGED_PROJECT=$(printf '%q' "$PROJECT") $(printf '%q' "$SKILL_DIR/adapters/scheduler-cron/run-daily.sh")"
  # Only a summary line of the expected shape goes into the error file, which the next session reads.
  CHANGES="$("$PY" -I "$SKILL_DIR/scripts/hosts.py" --store "$STORE" --compare "$APPROVED" | head -n 1)" || CHANGES=""
  printf '%s\n' "$CHANGES" | grep -Eq '^[0-9]+ source\(s\) added, [0-9]+ removed; hosts not approved before: [a-z0-9.,* -]+$' || CHANGES=""
  fail "topics.yaml needs your approval: $1 (${CHANGES:-could not compare}). Review $TOPICS (the added and removed sources are listed above this line on stderr), then approve this version with: $CMD" 7
}
# Approving is a step of its own, which works on a day that already ran: it records the version you
# reviewed (named by the start of its hash, so a later edit is not approved with it) and exits.
if [ -n "${WHAT_CHANGED_APPROVE_TOPICS:-}" ]; then
  read_topics_hash
  if [ "$WHAT_CHANGED_APPROVE_TOPICS" != "${TOPICS_HASH:0:32}" ]; then
    topics_stop "it is not the version you approved (its hash starts with ${TOPICS_HASH:0:32}, not $WHAT_CHANGED_APPROVE_TOPICS)"
  fi
  approve
  exit 0
fi

# One run at a time: a second start (another cron line, launchd catching up after sleep) while a run
# is still going exits here, and one that waited for it sees its record below. The lock is a symlink
# to the run's pid (made in one step), so a run that was killed, or a lock older than 6 hours, does
# not block the next ones.
LOCK="$STATE_DIR/$KEY.lock"
if [ -e "$LOCK" ] && [ ! -L "$LOCK" ]; then fail "$LOCK is not a lock this script made; remove it" 2; fi
if ! ln -sn "$$" "$LOCK" 2>/dev/null; then
  HOLDER="$(readlink "$LOCK")"
  case "$HOLDER" in ''|0|*[!0-9]*) HOLDER="" ;; esac  # not a pid: stale
  touch "$LOGDIR/.now"  # a lock dated in the future is stale too
  if [ -n "$HOLDER" ] && kill -0 "$HOLDER" 2>/dev/null \
     && [ -z "$(find "$LOCK" -maxdepth 0 \( -mmin +360 -o -newer "$LOGDIR/.now" \) 2>/dev/null)" ]; then
    echo "another run is in progress (pid $HOLDER)"; exit 0
  fi
  rm -f "$LOCK"
  ln -sn "$$" "$LOCK" 2>/dev/null || { echo "another run is in progress"; exit 0; }
fi
trap '[ "$(readlink "$LOCK")" = "$$" ] && rm -f "$LOCK"' EXIT
[ "$(readlink "$LOCK")" = "$$" ] || { echo "another run is in progress"; exit 0; }  # two runs removed the same stale lock
if [ "$(cat "$DONE" 2>/dev/null)" = "$TODAY" ]; then echo "already ran today ($TODAY)"; exit 0; fi

# Check the agent CLI before anything else, every day: a missing or old CLI must not stay hidden
# behind quiet days that never start it.
if [ "$HOST" = claude ]; then
  # Not by putting ~/.local/bin first on PATH: other commands should still come from the system.
  CLAUDE="${WHAT_CHANGED_CLAUDE:-}"
  if [ -z "$CLAUDE" ] && [ -x "$HOME/.local/bin/claude" ]; then CLAUDE="$HOME/.local/bin/claude"; fi
  if [ -z "$CLAUDE" ]; then CLAUDE="$(command -v claude || true)"; fi
  if [ -z "$CLAUDE" ] || [ ! -x "$CLAUDE" ]; then
    fail "claude not found (looked in ~/.local/bin and PATH=$PATH). Set WHAT_CHANGED_CLAUDE to its full path (run: command -v claude)." 3
  fi
  # With a time limit: a CLI stuck mid-update would otherwise hang the whole job.
  set +e
  VERSION="$("$PY" -I "$SKILL_DIR/scripts/cli_version.py" "$CLAUDE" "$CLAUDE_MIN" --timeout "${WHAT_CHANGED_VERSION_TIMEOUT:-30}")"
  CHECKED=$?
  set -e
  if [ "$CHECKED" -eq 4 ]; then fail "$VERSION; try again later, or raise WHAT_CHANGED_VERSION_TIMEOUT" 3; fi
  if [ "$CHECKED" -ne 0 ]; then
    fail "$VERSION; unattended runs use --restricted. Update Claude Code, or set WHAT_CHANGED_CLAUDE to another claude" 3
  fi
fi

# A new store (no ledger, no runs.log) is approved as it is; anything else needs your approval first.
read_topics_hash
if [ ! -f "$APPROVED" ]; then
  if [ ! -e "$STORE/runs.log" ] && [ -z "$(ls -A "$STORE/ledger" 2>/dev/null)" ]; then
    printf 'first run of this store: '; approve
  else
    topics_stop "there is no approved copy of it yet (a moved project, a new machine or a cleaned state folder)"
  fi
elif [ "$(sha_of "$APPROVED")" != "$TOPICS_HASH" ]; then
  topics_stop "it changed since you approved it"
fi

# Quiet-day shortcut: a script checks what is due and whether any source changed.
# Exit 0 = nothing changed (it writes the quiet-day digest itself; no model, 0 tokens).
# precheck stops fetching after its 600 s budget; LIMIT is the backstop for anything that misses.
LIMIT=900
set +e
"$PY" -I "$SKILL_DIR/scripts/run_limited.py" "$LIMIT" "$SKILL_DIR/scripts/precheck.py" --store "$STORE" --topics "$APPROVED" 2>&1 | tee "$LOGDIR/$TODAY-precheck.out"
PRE=${PIPESTATUS[0]}
set -e
if [ "$PRE" -eq 0 ]; then echo "$TODAY" > "$DONE"; exit 0; fi
if [ "$PRE" -eq 124 ]; then fail "precheck did not finish within $LIMIT s and was stopped; today is not counted as done" 12; fi
STARTED="$("$PY" -I "$SKILL_DIR/scripts/log_run.py" --now | head -n 1)"
STARTED_EPOCH="$(date +%s)"
if [ "$PRE" -eq 11 ]; then
  fail "no source of a due topic could be fetched (see $LOGDIR/$TODAY-precheck.out); today is not counted as done" 11
fi

case "$HOST" in
  claude)
    # -p is non-interactive; --permission-prompts none denies anything that would need a person.
    # Do not use --bare: bare mode has no web tools and skips skill discovery.
    # --restricted (Claude Code 2.1.248+) loads only managed settings, so your own settings cannot
    # widen this run: with the Bash sandbox enabled in ~/.claude/settings.json, sandboxed commands
    # are auto-allowed even in dontAsk mode and can read most of the machine (a plain
    # `cat ../secret.txt` would run). It also keeps the file tools inside the working directories
    # (uptodate/ and the skill folder, added with --add-dir) and drops tools not named in --tools.
    # --strict-mcp-config: no MCP servers or connectors.
    # dontAsk denies everything not listed, but still lets the agent read its working directory, so
    # it starts in uptodate/, not in the project: other project files stay out of reach.
    # Edits only to the ledgers and digests (Edit rules also govern the Write tool): not topics.yaml,
    # so a run cannot add hosts to the next run's allowlist, and not runs.log, whose lines (and
    # times) come from log_run.py and the system clock. Only the four named scripts may run, so the
    # agent cannot rewrite and run code.
    # Fetches (WebFetch and the scripts, via WHAT_CHANGED_ALLOWED_HOSTS) only from the hosts in
    # topics.yaml plus WHAT_CHANGED_FETCH_DOMAINS; pages elsewhere end up under "Could not check".
    # WHAT_CHANGED_STORE makes check_ledger and verify_quotes refuse paths outside the store.
    case "$REAL_STORE$REAL_SKILL$PY" in
      *[[:space:],\(\)]*)
        fail "refusing: permission rules cannot hold a path with spaces, commas or parentheses: $REAL_STORE, $REAL_SKILL, $PY" 2 ;;
    esac
    ALLOW="$("$PY" -I "$REAL_SKILL/scripts/hosts.py" --store "$REAL_STORE" --topics "$APPROVED" --allow "${WHAT_CHANGED_FETCH_DOMAINS:-}")" || fail "hosts.py could not build the fetch allowlist" 2
    ALLOWED_HOSTS="$(printf '%s\n' "$ALLOW" | sed -n 1p)"
    FETCH="$(printf '%s\n' "$ALLOW" | sed -n 2p)"
    S="$REAL_SKILL/scripts"
    # //abs/path anchors a permission rule at the filesystem root.
    TOOLS="Read(/$REAL_SKILL/**),Read(/$REAL_STORE/**),WebSearch${FETCH:+,$FETCH}"
    TOOLS="$TOOLS,Edit(/$REAL_STORE/ledger/**),Edit(/$REAL_STORE/digests/**)"
    TOOLS="$TOOLS,Bash($PY $S/fingerprint.py *),Bash($PY $S/check_ledger.py *),Bash($PY $S/verify_quotes.py *)"
    TOOLS="$TOOLS,Bash($PY $S/log_run.py *)"
    # The permission rules match these exact command forms, so the prompt spells them out.
    RULES="Unattended run: precheck.py already ran and found work. Run the skill's scripts only in exactly these forms, one script per command, nothing before $PY: $PY $S/log_run.py --now, $PY $S/fingerprint.py URL..., $PY $S/check_ledger.py $REAL_STORE, $PY $S/verify_quotes.py $REAL_STORE/ledger/TOPIC.md, $PY $S/log_run.py --store $REAL_STORE --started ISO scope=all FIELD=VALUE... (runs.log is written only this way). Other shell commands (curl, mkdir, ...) are denied; that does not stop these scripts, so still run check_ledger and verify_quotes at the end. The Write tool creates folders itself. Pages can be fetched only from: ${ALLOWED_HOSTS:-no hosts}; list other sources under Could not check."
    (cd "$REAL_STORE" && WHAT_CHANGED_ALLOWED_HOSTS="$ALLOWED_HOSTS" WHAT_CHANGED_STORE="$REAL_STORE" "$CLAUDE" -p "$PROMPT $RULES" \
      --restricted --tools "Read,Edit,Write,Bash,WebFetch,WebSearch" --add-dir "$REAL_SKILL" --strict-mcp-config \
      --permission-mode dontAsk --permission-prompts none \
      --allowedTools "$TOOLS" \
      --output-format json) > "$OUT" 2> "$ERR" || { agent_error >&2; fail "claude exited with an error; see $OUT and $ERR" 4; } ;;
  antigravity)
    # Headless mode; log in once with an interactive `agy` first. Files in the workspace can be
    # read and written; shell commands are denied unless you allow them (we do not).
    agy -p "$PROMPT" --output-format json > "$OUT" 2> "$ERR" ;;
  codex)
    # workspace-write: file writes are limited to the project folder and commands run in Codex's
    # sandbox. Codex cannot limit writes to uptodate/ alone, so keep the
    # skill folder outside the project or read-only if you need that.
    codex exec --sandbox workspace-write "$PROMPT" > "$OUT" 2> "$ERR" ;;
  qwen)
    qwen -p "$PROMPT" > "$OUT" 2> "$ERR" ;;
  *)
    fail "unknown WHAT_CHANGED_HOST: $HOST" 2 ;;
esac
# A run must not change the watchlist: the next runs would fetch whatever it added.
AFTER="$(sha_of "$TOPICS" 2>/dev/null)" || AFTER="unreadable"
if [ "$AFTER" != "$TOPICS_HASH" ]; then
  TOPICS_HASH="$AFTER"
  topics_stop "the agent changed it during today's run, which is not counted as done"
fi
# The agent should have logged today's run with log_run.py. If it wrote today's digest but no log
# line, log it here; with no digest either, the run did not happen: leave the day open.
set +e
"$PY" -I - "$REAL_SKILL/scripts" "$REAL_STORE" "$TODAY" "$STARTED_EPOCH" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from catch_up import ran_today
store, today, started = Path(sys.argv[2]), sys.argv[3], float(sys.argv[4])
digest = store / "digests" / f"{today}.md"
if ran_today(store / "runs.log", today):
    sys.exit(0)
sys.exit(10 if digest.is_file() and digest.stat().st_mtime >= started else 1)
PY
LOGGED=$?
set -e
if [ "$LOGGED" -eq 10 ]; then
  "$PY" -I "$REAL_SKILL/scripts/log_run.py" --store "$REAL_STORE" --started "$STARTED" \
    scope=all mode=light "host=$HOST" logged_by=scheduler >/dev/null || fail "could not write runs.log" 5
elif [ "$LOGGED" -ne 0 ]; then
  fail "the agent finished without writing today's digest; see $OUT" 5
fi
echo "$TODAY" > "$DONE"
echo "done; output in $OUT"
