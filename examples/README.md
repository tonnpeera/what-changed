# Example runs

Real output from the skill, kept so you can see what a store looks like before you run it. All runs happened on 2026-10-14 and ran the same topic.

| Folder | Host | What happened |
|---|---|---|
| [`codex-run/`](codex-run/uptodate/) | OpenAI Codex CLI | First run, `full` mode. |
| [`codex-run-2/`](codex-run-2/uptodate/) | OpenAI Codex CLI (bundled with the ChatGPT desktop app) | A second, separate first run, started with `bash evals/try-host.sh codex`. |
| [`antigravity-run/`](antigravity-run/uptodate/) | Google Antigravity desktop app (prompt sent in the app's chat) | First run, `full` mode. The app does not report tokens. The time in its `runs.log` line (01:22) was written by the model, not read from the clock: the folder was created at 01:23. |

## The topic

**`agent-skills-adoption`** (weekly, `full`): which tools support the Agent Skills format and where they look for skills. Its watchlist includes `https://agentskills.io/this-page-was-removed` on purpose, to check that a dead source is reported under "Could not check" and not as "No change". Each `topics.yaml` also lists a second topic that these runs did not cover.

## Reading the files

- `topics.yaml`: the watchlist. `ledger/<topic>.md`: one block per claim. `digests/2026-10-14.md`: what a person would read; each run of the day is a `## Run HH:MM` section. `runs.log`: one line per run.
- Claim IDs (`C-001`, …) are numbered per topic.
- A topic's **first run** (no ledger yet) reads more pages than later runs because there is nothing to compare against.
- The times carry the offset of the machine the runs were made on.

## Footers and edits

Each digest footer shows the check results at the time of that run; the current checker has more rules, so it reports more checks on the same ledgers. In the first Codex run the quote check could not reach any page from inside Codex's sandbox and said so ("0/0 checkable, 12 unreachable"); checked afterwards from outside, all 12 quotes are on their pages.

In `codex-run-2/runs.log` the `tokens=` field was filled in from the host's own report by `evals/host_tokens.py` (the agent cannot see its usage while running). In each `topics.yaml`, the comment on the first line and the question of the second topic (which these runs did not cover) were reworded. Nothing else in these folders was edited after the runs.

## Your own runs

`bash evals/try-host.sh <host>` writes to `examples/local-runs/` (git-ignored).
