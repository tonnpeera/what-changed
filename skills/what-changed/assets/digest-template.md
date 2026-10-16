# Digest YYYY-MM-DD

<!-- Omit empty sections. Quiet-day form (every due topic unchanged):
## Run HH:MM (light) — No change
- [topic-id] fingerprints unchanged: source → fingerprint; next due: DATE
- not due: [topic-id] (next: DATE)
Run stats: … -->

## Run HH:MM (mode: light|full · ran at: actual time, if a catch-up run)

**In three lines**
1. …
2. …
3. …

### New
- **C-xxx** [topic-id] claim — confidence: level — [source](url) (read)

### Changed / superseded
- **C-yyy → C-xxx** [topic-id] old value → new value — confidence: level — [source](url) (read)

### Disputed
- **C-xxx** [topic-id] what disagrees with what, in one line

### No change
- [topic-id] fingerprints unchanged: source → fingerprint

### Could not check
- [topic-id] source — reason (timeout / HTTP 403 / bot check / no web tool)

### Due for review
- **C-xxx** [topic-id] review_by YYYY-MM-DD — what to re-check

### Proposed topics (not added until you say yes)
- …

---
Run stats: topics due x/y · pages read n · searches n · search tool used: … · tokens: n (if known) · check_ledger: passed x/y · quotes found on page: x/y (+ n unreachable, n truncated, not counted)
Interpretation is marked as such; everything else is what the sources say.
