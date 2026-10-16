# Benchmark: the skill against a plain agent (2026-10-15)

**Question.** Given old notes on a topic, does the skill find what has changed since, better than an agent that just searches the web?

The raw answers, judge verdicts and scripts are not published. This page records the setup, the criteria fixed in advance, every measure and the caveats.

## Setup

- **Items.** 27 items drawn at random (fixed seed) from official pages chosen in advance: AI model deprecation dates (Claude, OpenAI, Gemini), Python, Node.js and Kubernetes release status, three central-bank rates, the Thai minimum wage and Let's Encrypt certificate rules. They were grouped into 6 topics.
- **Notes.** Each item was one note dated between 2025-03-01 and 2026-05-31; both sides got the same note text and date. 18 items had changed and 9 had not, including 2 traps where a headline number stayed the same but something else changed.
- **Agents.** Both sides were Claude Sonnet sub-agents in Claude Code with only web search and page fetching. **The skill also read the official source URLs listed in its topic file, as in normal use; the plain agent had to find sources itself.** The plain agent was asked "What changed about this since <date>? Cite sources." and to copy exact words from each page.
- **Fixed in advance.** The protocol, pass criteria and answer keys were written down and committed to version control before either side ran. The keys were written by the experimenter, a Claude model that already knew the skill.
- **Judging.** Two Sonnet judges, each starting with an empty context, compared the two answers for every item against the key, with labels hidden and the order randomised.
- **Version.** The skill as it was on 2026-10-15 (see Caveats).

## Results

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/benchmark-dark.svg">
  <img alt="Bar chart: what-changed versus a plain agent on 27 items. Quality, higher is better: changes caught 18/18 vs 17/18, current value right 16/18 vs 15/18, unchanged items left alone 9/9 vs 8/9, quotes found 47/47 vs 24/26, preferred by both judges 13 vs 3 of 16. Cost, lower is better: 507k vs 89k input tokens per item (5.7 times), 4.6 vs 1.0 minutes per topic (4.6 times)." src="images/benchmark-light.svg" width="100%">
</picture>

| Measure | Skill | Plain agent |
|---|---|---|
| Changes caught | 18 of 18 | 17 of 18 |
| Changes caught with the current value right | 16 of 18 | 15 of 18 |
| Unchanged items correctly left alone | 9 of 9 | 8 of 9 (the miss was a trap item) |
| Items with a quote found on the cited page | 25 of 27 | 20 of 27 |
| Quotes in the answers found on the cited page | 47 of 47 checkable (5 not checkable: 4 PDF, 1 page that would not load) | 24 of 26 |
| Citation score (0–2, mean of both judges) | 1.98 | 1.52 |
| Accuracy score (0–2, mean of both judges) | 1.94 | 1.87 |
| Input tokens processed, all 27 items, cache reads included | 13.7M, 94% cache reads (about 507k per item) | 2.4M, 92% cache reads (about 89k per item) |
| Wall-clock time per topic | 4.6 minutes on average | 1.0 minute on average |

- *Current value right*: both judges said the answer gives the current value in the key.
- *Accuracy*: 2 means right on changed or unchanged and on the current value, 1 means partly right, 0 means wrong.
- *Citation*: 2 means an official page that supports the answer, with quotes found on it; 1 means weak support (a secondary source, or a quote that was not found or does not support the claim); 0 means none.
- Quotes are checked by script after normalising whitespace and trailing punctuation (`verify_quotes.py`). Across the skill's whole ledger, not only the answers, 85 of 85 checkable quotes were found (5 PDF and 1 unreachable quote excluded).
- Tokens are counted as in [results.md](results.md#cost). Cache reads cost a fraction of normal input, so 5.7 times the tokens does not mean 5.7 times the price.

**Blind preference.** The judges preferred the skill on 13 items and the plain agent on 3, with 11 ties (two-sided sign test on the 16 items that were not ties, p = 0.021). An item counts as a win only when both judges agree, so the 11 ties include 3 items where the judges disagreed (they agreed on 24 of 27, Cohen's kappa 0.81).

## Criteria written down before the runs

| Criterion | Result | Passed |
|---|---|---|
| Changes caught ≥ 80% | 18 of 18 (100%) | yes |
| Current value right in ≥ 90% of changes caught | 16 of 18 (88.9%) | **no** |
| Unchanged items correctly left alone ≥ 90% | 9 of 9 | yes |
| Claims rated `high` right ≥ 95% | 19 of 20 | yes |
| Quotes found ≥ 90% | 47 of 47 checkable | yes |
| More blind-preference wins than losses, p < 0.05 | 13 to 3, p = 0.021 | yes |
| Install in ≤ 10 minutes | about 22 seconds of agent time for a fresh session that saw only the repository to install the skill and set up its first topic; first full run about 1.5 minutes | yes |

The skill passed 6 of 7. The miss, current value right: in one item it said Node.js 24 had reached long-term support but gave no start date; in the other it said a model's shutdown date had passed but did not confirm that the shutdown happened.

The skill's instructions require two general rules that address these misses: a claim that a value changed must state the date the new value took effect (or say that the source gives none), and an event whose scheduled date has passed counts as happened only with a quote from a page that says so; otherwise the claim says that no confirmation was found and is rated at most `low`. `check_ledger.py` checks the first rule. Both rules were added after the benchmark; their effect has not been measured.

## How to read it

The accuracy gap is small (1.94 against 1.87), and no significance test was run on it. The largest gap is in citations (1.98 against 1.52). The skill quoted a source on every item, and on 25 of 27 a quote was found on the cited page. The plain agent quoted a source on 22 of 27 items, and on 20 of those a quote was found. Part of this gap probably comes from the source list the skill was given. The skill also costs more: about 5.7 times the input tokens and about 4.6 times the time.

## Caveats

- **Small n.** The two sides' 95% Wilson intervals overlap on every rate: changes caught 82–100% against 74–99%, current value right 67–97% against 61–94%, wrong alarms on unchanged items 0–30% against 2–43% (only 9 unchanged items).
- **The judges are models (Sonnet), not people,** the same model as the agents tested. Blinding was imperfect: the skill's fixed phrasing may have let judges tell which answer was which.
- **One run per topic, one model, one host.** Run-to-run variation was not measured.
- **Unequal sources.** Only the skill had a list of official pages to check (see Setup).
- **Version.** The benchmark used the skill as it was on 2026-10-15; the current version has not been benchmarked.
