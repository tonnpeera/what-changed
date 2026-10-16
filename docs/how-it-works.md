# How it works

## Why a ledger, not a list of links

When you act on information that changes, a list of today's links is not enough. You need three more things, and the ledger keeps them:

1. **What you already knew.** The ledger remembers that "Model X costs $Y" was true last week and is superseded today, and keeps both.
2. **How you know it.** Each source is labelled `read` (opened and read, with a verbatim quote), `search-snippet` (seen only in search results or someone else's summary) or `unverified` (memory, old notes).
3. **How sure to be.** Each claim gets `high / medium / low / very-low` with a one-line reason, under hard ceilings: nothing rests on search snippets alone above `low`; nothing rests on blogs and social posts alone above `very-low`.

## Terms

| Term | Meaning |
|---|---|
| claim | One checkable statement with a date or version, e.g. "Tool X 2.4, released 2026-03-01, adds an offline mode". IDs (`C-001`…) are per topic. |
| ledger | One Markdown file per topic (`uptodate/ledger/<topic>.md`) that holds every claim with its sources, quote, confidence and history. |
| digest | The short report of one day (`uptodate/digests/<date>.md`): new, changed, disputed, could not check. |
| status | `active`, `superseded` (replaced by a newer claim, never deleted), `retracted`, `disputed` |
| T1–T4 | Source tiers: T1 official/primary (docs, changelog, pricing page, law text) · T2 original reporting or research · T3 reputable summaries · T4 blogs, forums, social, marketing |
| `light` / `full` | Per-topic run mode. `light` (default) reads only sources whose fingerprint changed; `full` re-reads and re-checks everything (good for a topic's first run or a weekly deep check) |
| fingerprint | A cheap "did it change?" signal per source, made by `scripts/fingerprint.py`: newest changelog version, release tag, feed item, or a page hash |
| precheck | `scripts/precheck.py`: decides without a model whether anything is due or changed; if not, writes the "No change" digest itself |

## What a run does

1. **Decides what is due** from your watchlist (cadence, claims past their review date, low-confidence claims to re-check). No guessing.
2. **Checks fingerprints first.** Nothing changed and nothing due → one line, done.
3. **Reads what changed**, preferring primary sources, in the topic's region and language (a US-centred search index is a poor tool for a local regulator or a law written in another language).
4. **Compares claims with the ledger**: new, reconfirmed, changed (the old one is superseded, not deleted), disputed.
5. **Verifies new and changed claims**: trace to the primary source, run at least one search for counter-evidence, count independent sources.
6. **Writes** the ledger, a short digest and a log line (its time comes from the system clock, not the model), then checks itself with two scripts.

**"Could not check" is never "no change".** A blocked page, a bot check or a timeout is reported as such. A topic none of whose sources could be fetched is not counted as checked and stays due; a source that fails 3 runs in a row is reported as possibly gone.

The way evidence is weighed draws on established practice for reviewing evidence: Cochrane rapid reviews (write down the method before searching, record every search), GRADE (start from the strength of the source, then downgrade for specific doubts), SIFT and lateral reading (check who is behind a source before trusting it, trace claims to the original) and Analysis of Competing Hypotheses (look for the evidence that would prove you wrong). The working version is in [`references/method.md`](../skills/what-changed/references/method.md); file formats are in [`references/ledger-format.md`](../skills/what-changed/references/ledger-format.md).

## Checks you can run without trusting the model

`$SKILL` is the folder you copied, for example `.claude/skills/what-changed`.

| Command | What it checks |
|---|---|
| `python3 $SKILL/scripts/check_ledger.py uptodate/` | About a dozen rule checks per claim (format, unique IDs, superseded claims point somewhere, every `read` source has a short verbatim quote, confidence within its ceiling), and that run times in `runs.log` and the digests are not later than the files were written. Prints passed/total |
| `python3 $SKILL/scripts/verify_quotes.py uptodate/` | Re-downloads each `read` source and looks for the quote on the page. Plain HTTP and string matching; no model involved. Catches page-reading tools that paraphrase or invent sentences |
| `python3 $SKILL/scripts/fingerprint.py URL…` | Prints the fingerprint of each URL |
| `python3 $SKILL/scripts/precheck.py --store uptodate/` | Exit codes in the [README](../README.md#quick-start-about-5-minutes) |
| `python3 $SKILL/scripts/log_run.py --now` | Prints the time from the system clock; with `--store` it appends the `runs.log` line (the agent uses it so that times are never guessed) |

All scripts use only the Python 3 standard library. The test suite: `python3 -m unittest discover -s tests`.

## Good to know

- **Running inside a sandbox** (for example Claude Code's sandbox): network access is allowed per host, and a refused host looks like a dead site to a plain script. The scripts report it as `blocked-local … allow this host`, not as a failure of the source. Behind such a proxy, a domain that does not exist at all is reported the same way. `python3 $SKILL/scripts/hosts.py --store uptodate` prints the watchlist's hosts (needed every day) and, separately, other hosts cited in the ledgers for you to review before allowing.
- **When the scripts cannot run** (no shell, or their network is blocked), the agent writes `(none — script could not run)` as a source's fingerprint rather than a value of its own; the next precheck then asks the agent for a new baseline instead of reporting a change.
- **`recheck_low: true`** re-checks low, very-low and disputed claims when the topic is due by its cadence (or when a claim reaches its own `review_by`), even if no source changed. It never makes a weekly or monthly topic run more often. Cadences are 1, 7 and 30 days.
- **Run the daily update in a fresh session or a sub-agent.** Every model call re-sends the whole conversation, so the cost of the same small job grows with what is already in the session. In one test, a routine run inside a session that already held about 285k tokens of context processed about 3.9M input tokens (93% from cache) to read a single page; the same kind of quiet day in a fresh sub-agent processed about 0.37M. The schedulers in `adapters/` start a new session each time.
- **Downloads that arrive incomplete** (shorter than the server said) are retried and then reported as `partial`, so a truncated page is never mistaken for a changed one.
- **Very large pages.** A page-reading tool may read only the start of a long file (for example a changelog of about 1 MB). The newest entries are usually at the top, so this is fine for "what is new", but a first run will not cover the whole history. A release feed (`/releases.atom`) is often a better source.
- **Certificates with Python from python.org on macOS.** Its fallback CA file, `/etc/ssl/cert.pem`, lacks some newer roots (for example the one `www.ecb.europa.eu` uses), so such sources show as unreachable. Set `SSL_CERT_FILE` to a CA bundle that includes them.
- **PDF sources.** `fingerprint.py` can tell that a PDF changed (it hashes the file like a page) but not what changed, and `verify_quotes.py` cannot check quotes in PDFs, so claims from PDFs need a human check.
