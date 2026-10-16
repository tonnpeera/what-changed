# File formats

Plain text on purpose: readable without tools, diffable in git, editable by any agent.

## topics.yaml

```yaml
topics:
  - id: claude-code-updates          # lowercase, hyphens; becomes ledger/<id>.md
    question: "What changed in Claude Code and the Claude API that affects how I use them?"
    sources:                         # trusted, ideally primary; fingerprinted every run
      - https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md
      - https://docs.claude.com/en/release-notes/overview
    cadence: daily                   # daily | weekly | monthly
    counts_as_change: "new version, new/removed feature, price or limit change, deprecation date"
    mode: light                      # light | full
    budget: { pages: 5, searches: 4 }
    recheck_low: true                # re-verify low/disputed claims when due
    region: global                   # optional; ISO country code (DE, JP, BR…) or global (default)
    languages: [en]                  # optional; default [en]. Add the local language for local topics
```

## ledger/<topic-id>.md

```markdown
---
topic: claude-code-updates
question: "What changed in Claude Code ..."
last_run: 2026-10-14
next_claim_id: 13
---

## Source state
- https://raw.githubusercontent.com/.../CHANGELOG.md — fingerprint: "2.1.301" — checked: 2026-10-14 — ok
- https://docs.claude.com/en/release-notes/overview — fingerprint: "October 9, 2026" — checked: 2026-10-14 — failed: HTTP 403

## Claims

### C-012 · Claude Code reads AGENTS.md when the project has no CLAUDE.md
- status: active
- confidence: high — official changelog, read
- sources:
  - [CHANGELOG 2.1.277](https://...) — T1 — read — quote: "exact words copied from the page"
  - [blog post](https://...) — T3 — search-snippet
- counter-evidence: "AGENTS.md ignored Claude Code" (2026-10-14) → none found
- asserted_by: agent
- first_seen: 2026-09-18 · last_confirmed: 2026-10-14 · review_by: 2027-01-14
- superseded_by: —
```

Field rules:
- **ID** `C-NNN`, never reused. Heading is `### C-NNN · <one-line claim>`.
- **status**: `active` · `superseded` (needs `superseded_by`) · `retracted` · `disputed`.
- **confidence**: level, em dash, one-line reason.
- **sources**: one per line: `[label](url) — T1..T4 — read|search-snippet|unverified`, and for `read`: `— quote: "…"` (≤ 25 words, verbatim, straight double quotes).
- **asserted_by** (optional): `agent` by default; set `user-confirmed` when a person has checked the claim.
- **note** (optional): caveats that do not fit the one-line claim, e.g. "rollout announced; may not be on every account yet".
- **counter-evidence**: the query, date and outcome; or `not searched (budget)`, which caps confidence at `medium`.
- Dates are ISO `YYYY-MM-DD`. Times in digests and `runs.log` are the run's **start** time, local, with offset, read from the system clock with `scripts/log_run.py --now` (a model's guess of the time is often wrong). `scripts/log_run.py` writes the `runs.log` line itself.
- In *Source state*, cite the URL you actually fetched. If you read a text twin of a watchlist URL (`.md`, raw file, feed), list it as `watchlist-url → read-url` (`->` also works).

## digests/YYYY-MM-DD.md
See `assets/digest-template.md`.

## runs.log
One line per run, tab-separated:
```
2026-10-14T07:00:12+00:00	scope=all	mode=claude-code-updates:light,agent-skills:full	host=<agent name>	due=2/3	checked=claude-code-updates,agent-skills	changed=1	new=3	superseded=1	could_not_check=1	pages=4	searches=3	tokens=<if known>
```
Write it with `scripts/log_run.py --store <store> --started <ISO> scope=all mode=… …`, which adds the timestamp. `scope=all` when the run was asked for all due topics (a scheduled or catch-up run), `scope=topics` when the user named topics. Only `scope=all` lines count as "today's run" for the scheduler and the catch-up hook. A run that found every due topic already done today writes `scope=all	checked=none	skipped=already-ran-today`.
