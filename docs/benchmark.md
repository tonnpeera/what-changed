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

# Round 2: the cheaper skill against a plain agent (2026-10-16)

> Rounds 2 and 3 tested a development version of the skill that adds `gather.py` and `finish.py` (and, from round 3, gzip decoding in `net.py`). That version is not part of this repository: the published skill is the round 1 version with later fixes. Since neither round showed it to be better than a plain agent, it was not released.

**Question.** After changes aimed at cost (below), does the skill still match a plain agent, at a cost of at most 2.5 times the input tokens and 2 times the time? Targets, criteria and the answer key were written down and committed before either side ran, as in round 1.

**What changed in the skill.** Round 1's skill made 132 model calls against the plain agent's 33, and each call re-sends the whole conversation. The agent wrote its own download code and read pages piece by piece (29% of its tokens), and edited the ledger in many small steps with checks in between (32%). Round 2's skill adds `gather.py`, which downloads every source once and prints only the lines that mention each claim, and `finish.py`, which runs the checks and records the run in one command. It also tells the agent to batch tool calls and to give, for a changed value, what the same source says beside it (values in between, successor, next announced change).

**Setup.** As in round 1 (Sonnet sub-agents in Claude Code with web search and page fetching; only the skill had the topic's list of official pages; two blind Sonnet judges with the key), with new items: 20 items drawn from 20 templates over 4 topics (Go, PHP and Ruby releases; PostgreSQL, Debian and Ubuntu; three central-bank rates; Java, Django, .NET and Rails), with note dates drawn at random. 3 were dropped before the runs (the official page could not be read, or the change was within 3 days of the note date or of the run), leaving 17: 12 changed, 5 unchanged. A one-topic pilot on round-1 items was used to fix the skill before it was frozen; it is not counted.

| Measure | Skill | Plain agent |
|---|---|---|
| Changes caught | 12 of 12 | 12 of 12 |
| Changes caught with the current value right | 11 of 12 | 11 of 12 |
| Unchanged items correctly left alone | 4 of 5 | 5 of 5 |
| Quotes found on the cited page | 40 of 40 checkable (4 not checkable) | 22 of 23 (1 not checkable) |
| Accuracy score (0–2, mean of both judges) | 1.91 | 2.00 |
| Citation score (0–2, mean of both judges) | 1.82 | 1.74 |
| Preferred by both judges | 5 | 6 (6 ties; sign test p = 1.0) |
| Input tokens processed, cache reads included | 4.78M (about 281k per item) | 1.73M (about 102k per item) |
| Model calls per topic (mean) | 12 | 6 |
| Wall-clock time per topic (mean) | 3.1 minutes | 1.2 minutes |

**Against the targets.**
- Input tokens: 2.8 times the plain agent (round 1: 5.7 times). **Target of 2.5 times missed.**
- Time: 2.6 times (round 1: 4.6 times). **Target of 2 times missed.**
- Accuracy: not lower than the plain agent? **No**: 1.91 against 2.00. Per item, the judges scored the skill lower on 2 items and the same on 15.
- Citations: not lower? Yes, 1.82 against 1.74, a small gap.
- Better than the plain agent in a measurable way? **No.** Neither accuracy nor preference shows a difference (5 wins against 6).

**Where the skill lost.**
- One false alarm: the agent reconfirmed an unchanged claim (Ruby 4.0 is the newest stable branch) but listed it under "Changed" in the digest, so it counted as reported changed.
- Answers made of the skill's notes read worse than the plain agent's prose. The judges called one "garbled" and preferred cleaner answers when both were right. The new rule to give the whole change made some notes longer and full of remarks about the process ("as relayed by the page tool").
- When a source could not be downloaded by the scripts (rba.gov.au failed the TLS check), the agent fell back to a summarising page tool, and the values in between came out incomplete.

**Caveats.** n = 17 with only 5 unchanged items, so every interval is wide: changes caught 76–100% for both, false alarms 4–62% against 0–43%. One run per topic. The plain agent did better here than in round 1 (citation 1.74 against 1.52), probably because these topics have well-known official pages. The quote check of the benchmark itself was changed after the runs and before judging so that a truncated download counts as not checkable rather than as a missing quote, for both sides (3 of the skill's quotes on federalreserve.gov had come out as missing). The experimenter wrote the changes being tested.

# Round 3: watching the same topics over several runs (2026-10-16)

**Question.** Rounds 1 and 2 measured one answer per item. The skill's claimed advantage is in *repeated* runs: on a run where no source changed, `precheck.py` answers without a model (0 tokens), and the ledger keeps answers stable from run to run. Over several runs, is the skill cheaper than a plain agent that is given its own previous answer, without missing changes or being less accurate? Hypotheses, pass criteria, the expected outcome and what the sample size cannot show were written down and committed before any snapshot content was read; the answer key was committed before any agent ran.

**Setup.**
- **Pages and rounds.** Four official pages (Go release history, Python devguide versions, Node.js previous releases, Bank of Canada policy rate), replayed from Internet Archive (Wayback Machine) snapshots on six dates a week apart, 2025-09-10 to 2025-10-15 (rounds R0–R5). For each page and round the snapshot is the last capture on or before that date. The window was chosen knowing that some changes would fall in it; no snapshot was chosen by hand.
- **Items.** Six facts fixed before reading the pages: the latest Go release, the status of Python 3.14 and Python 3.9, the latest Node.js 22 release, the status of Node.js 24, and the Bank of Canada rate. The key is what each round's snapshot says: 36 item-rounds, 5 of them changed (the rate cut on 2025-09-17 seen at R2; Go 1.25.2, Python 3.14 to bugfix and Node.js 22.20.0 at R4; Go 1.25.3 at R5). Node.js 24 is a trap: its line gets new releases every round, but its status stays "Current".
- **Both sides got the same pages and no web search** (round 1 and 2 gave only the skill a source list). Both were told the date of the round and that the pages are archived copies standing in for live ones. Both were Claude Sonnet sub-agents in Claude Code. The plain agent read the pages with WebFetch or curl and, from R1 on, got its own JSON answer from the previous round. The skill side ran as its scheduler does: `precheck.py` first, and an agent only when precheck asked for one.
- **Clock.** The skill's scripts use the system clock, so the frozen copy under test got a small shim that sets "today" to the round's date (like `faketime`). Without it, the first R0 run read September 2025 pages on a 2026 date, rated four claims `low` because their scheduled dates had "passed", which would have woken the agent every round. That run was discarded and R0 was run again on both sides (see Deviations).
- **Judging.** Two Sonnet judges with empty contexts, labels hidden and the A/B order randomised per judge, scored each item-round against the key. Whether an answer *reported a change* was read by script (the skill's digest headings Changed/Superseded/Disputed; the plain agent's `verdict`).

**Results.**

| Measure | Skill | Plain agent |
|---|---|---|
| Rounds R1–R5 that needed a model | 4 of 5 (R1 answered by precheck alone) | 5 of 5 |
| Input tokens R1–R5, cache reads included | 6.49M (8.18M with the failed R2 attempt) | 2.09M |
| Model calls per round R1–R5 (mean) | 14 | 6 |
| Wall-clock per round R1–R5 (mean) | 4.1 minutes (precheck: 7–35 seconds) | 1.3 minutes |
| Changes caught, current value right (both judges) | 5 of 5 | 5 of 5 |
| Unchanged item-rounds not reported as changed (R0–R5) | 31 of 31 | 29 of 31 (Node.js 24 at R4 and R5) |
| Unchanged item-rounds with the current value right (both judges) | 31 of 31 | 31 of 31 |
| Accuracy score (0–2, mean of both judges) | 2.00 | 1.94 |
| Preferred by both judges | 2 | 2 (32 ties or split; judges agreed on 31 of 36) |
| Round 0 (setup), input tokens | 0.94M | 0.44M |

**Against the criteria written before the runs.**

| | Criterion | Result | Passed |
|---|---|---|---|
| H1 | Watching cost R1–R5: skill ≤ 0.5 × plain | 3.11 × (3.92 × with the failed attempt) | **no** |
| H2 | Every topic-round with a change wakes the agent | 3 of 3 | yes |
| H3 | Unchanged item-rounds left alone: skill ≥ plain | 31 against 29 of 31 (Fisher p = 0.49) | yes |
| H4 | Changes caught with the value right: skill ≥ plain | 5 against 5 of 5 | yes |
| H5 | Unchanged item-rounds with the value right: skill ≥ plain | 31 against 31 of 31 | yes |

By the rule fixed in advance (better = all five pass; H2–H5 pass but H1 fails = "not worse, but not cheaper"), **the skill was not shown to be better than a plain agent at watching. It was not worse on any quality measure, and it cost about three times as much.**

**Why it cost more.**
- **Precheck saved one run in five.** R1 was answered with 0 tokens. In R3 a page hash changed with no change in any fact (the Python devguide and the Bank of Canada page add unrelated text between captures). The other wakes came from review dates the agent sets itself: in R2 it had set the rate claim's review to the day after the scheduled announcement (and the rate had changed); in R4 the Python claims were due on the scheduled release date (and three values had changed); in R5 the three claims changed at R4 had a review date one week ahead (one of them, Go, had changed again).
- **The skill's agent runs are expensive.** They averaged 1.6M input tokens against the plain agent's 0.42M. Two runs (R3, R5) took 20–25 calls, mostly because the sandbox proxy kept failing downloads from the archive and the agent retried, while the plain agent's curl calls went through in the same period. The first R2 attempt failed outright for that reason and was rerun once, as the protocol allows.
- **Daily watching (script only, secondary).** Over the 35 days from 2025-09-10 to 2025-10-15, the day's latest snapshot changed a page fingerprint on 10 days. With the round costs above, a daily watch would cost the skill about 10 × 1.62M = 16.2M against 35 × 0.42M = 14.6M for the plain agent (1.11 ×). This leaves out wakes from review dates, which would add to the skill's side.

**Where each side lost.**
- The plain agent twice reported Node.js 24 as changed because its latest release number moved, though its status (the question) stayed "Current". The skill kept the status and noted the new release number.
- The judges preferred the plain agent's answer on items where both were right, when the skill's answer carried a ledger note such as "Replaces (prerelease)" on a round with no change, which they found confusing.

**Caveats.**
- **Small n**, as stated before the runs: 5 changed item-rounds, 31 unchanged. The false-alarm difference (0 against 2) is not significant. Accuracy is near the ceiling on both sides.
- **One window, four pages, one model, one run per round.** Network failures in the sandbox raised the skill's cost; on a machine without them its agent runs would likely be cheaper, but that was not measured.
- **Replay, not live use.** The pages are archived copies. Some "unchanged" rounds come from the archive having no newer capture.
- **The judges are Sonnet, the same model as the agents.** The experimenter wrote the skill.
- **Deviations from the protocol** (each recorded with the side it favoured): the skill's downloader could not read gzip bodies, which the archive sends unasked for 17 of 24 page-rounds; this was fixed before freezing the skill (`net.py` now decompresses them, favours the skill). The clock shim and the rerun of R0 (favours the skill compared with not fixing it). One rerun of the skill's R2 after a tool failure (favours the skill; both cost ratios are given). The script that reads "reported a change" first counted any heading containing the word "changed"; it was narrowed to headings that are Changed/Superseded/Disputed, as the protocol says, after the R0–R1 results were seen and before judging. With the first version the skill would have had 6 false alarms at R0 (25 of 31, and H3 would fail).
