#!/usr/bin/env bash
# Maintainer script: try the skill in an agent host, on a fresh copy of the example watchlist.
# Not needed to use the skill.
#   bash evals/try-host.sh antigravity|codex|codex-ollama|qwen|claude [topic-id]
# Installs the skill for this repo only (.agents/skills and .claude/skills symlinks, git-ignored),
# runs one topic headless, saves the host's output, then runs the offline checks.
set -euo pipefail

HOST="${1:?usage: try-host.sh antigravity|codex|codex-ollama|qwen|claude [topic-id]}"
TOPIC="${2:-agent-skills-adoption}"
case "$HOST" in antigravity|codex|codex-ollama|qwen|claude|antigravity-check) ;; *) echo "unknown host $HOST" >&2; exit 2 ;; esac
REPO="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y-%m-%d)"
STORE="$REPO/examples/local-runs/${HOST%-check}-$STAMP/uptodate"
check() {
  python3 "$REPO/skills/what-changed/scripts/check_ledger.py" "$STORE" || true
  python3 "$REPO/skills/what-changed/scripts/verify_quotes.py" "$STORE" || true
  ls "$STORE/digests"
}
case "$HOST" in *-check) check; exit 0 ;; esac

mkdir -p "$REPO/.agents/skills" "$REPO/.claude/skills" "$STORE/ledger" "$STORE/digests"
for d in .agents .claude; do ln -sfn "$REPO/skills/what-changed" "$REPO/$d/skills/what-changed"; done
[ -f "$STORE/topics.yaml" ] || cp "$REPO/examples/codex-run/uptodate/topics.yaml" "$STORE/topics.yaml"

PROMPT="Use the what-changed skill: run the topic $TOPIC now. Store: $STORE. Today is $STAMP."
# On macOS the ChatGPT desktop app bundles the Codex CLI; use it if codex is not on PATH.
if [ -z "${CODEX_BIN:-}" ]; then
  if command -v codex >/dev/null; then CODEX_BIN=codex
  else CODEX_BIN="/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"; fi
fi
AGY="$(command -v agy || true)"; [ -z "$AGY" ] && [ -x "$HOME/.local/bin/agy" ] && AGY="$HOME/.local/bin/agy"
OUT="$STORE/host-output.json"
if [ "${TRY_HOST_DRY_RUN:-}" = 1 ]; then run() { echo "DRY RUN:" "$@"; }; else run() { "$@"; }; fi
cd "$REPO"
case "$HOST" in
  codex)  run "$CODEX_BIN" exec --sandbox workspace-write --skip-git-repo-check "$PROMPT" > "$OUT" 2>&1 ;;
  codex-ollama)  # a local model through Ollama; set OLLAMA_MODEL to a model you have pulled
          run "$CODEX_BIN" exec --oss --local-provider ollama -m "${OLLAMA_MODEL:?set OLLAMA_MODEL}" \
            --sandbox workspace-write --skip-git-repo-check "$PROMPT" > "$OUT" 2>&1 ;;
  qwen)   run qwen -p "$PROMPT" > "$OUT" ;;
  antigravity)
          if [ -n "$AGY" ]; then
            # Headless reads/writes workspace files; shell commands are soft-denied, so the
            # skill runs without its scripts. Needs one interactive `agy` login first.
            run "$AGY" -p "$PROMPT" --output-format json > "$OUT"
          else
            echo "Antigravity CLI (agy) not found. Either install it (see antigravity.google/docs/getting-started,"
            echo "CLI tab) and log in once with: agy   -- or use the app:"
            echo "  1. Open Antigravity (or Antigravity IDE) and open the folder $REPO"
            echo "     (the skill is linked at $REPO/.agents/skills/what-changed; trust the workspace)"
            echo "  2. Send this message:"; echo; echo "  $PROMPT"; echo
            echo "  3. Then run: bash evals/try-host.sh antigravity-check"; exit 0
          fi ;;
  claude) S="$REPO/skills/what-changed/scripts"
          run claude -p "$PROMPT" --permission-mode dontAsk --permission-prompts none \
            --allowedTools "Read(/examples/**),Read(/skills/**),WebSearch,WebFetch,Edit(/examples/local-runs/**),Bash(python3 $S/log_run.py *),Bash(python3 $S/fingerprint.py *),Bash(python3 $S/check_ledger.py *),Bash(python3 $S/verify_quotes.py *)" \
            --output-format json > "$OUT" ;;
  *) echo "unknown host $HOST" >&2; exit 2 ;;
esac

echo "host output: $OUT"
[ "${TRY_HOST_DRY_RUN:-}" = 1 ] || python3 "$REPO/evals/host_tokens.py" "$HOST" "$OUT" "$STORE" || true
check
