# Method: how to weigh what you find

A compact, practical version of established evidence-appraisal methods, tuned for *fast-changing facts* (products, prices, policies, releases, markets) checked on a schedule. It borrows from Cochrane rapid reviews (protocol first, documented searches), GRADE (start level, then downgrade for specific concerns), SIFT / lateral reading (check the source before trusting it), and Analysis of Competing Hypotheses (look for evidence that would prove you wrong).

## 1. Source labels (how you know)

| Label | Meaning | Allowed as basis for |
|---|---|---|
| `read` | You opened the page and read the relevant text yourself. Must carry a verbatim quote. | any level |
| `search-snippet` | Search result text, someone else's summary, an abstract quoted elsewhere, or a sub-agent's report you did not re-open. | at most `low` |
| `unverified` | From memory, inference, or the user's older notes. | at most `low`, and say so |

Opening a page is not the same as the claim being true. Labels describe *how you know*, not *whether it is right*. Avoid tick marks or "verified" badges; they read as "proven".

**Page-reading tools can paraphrase.** Some fetch tools return a summary written by a smaller model, which may contain sentences that are not on the page. For any claim a conclusion depends on, ask for the exact sentence, or use a tool that returns raw page text. The quote in the ledger is what makes this checkable later.

A search tool that returns a model-written summary instead of result snippets gives you `search-snippet` evidence at best. If two model-based tools (a page summariser and a search summary) disagree about what a page says, treat the claim as `disputed` until you read the raw text.

**A tool failing to reach a page does not mean the thing does not exist.** Blocked, paywalled, bot-checked or JS-only pages go under "Could not check".

## 2. Source tiers (what kind of source)

| Tier | Examples (for fast-changing topics) | Use |
|---|---|---|
| T1 | Official changelog, documentation, release notes, pricing page, regulator/government text, the paper itself | Basis for claims |
| T2 | Original reporting with named sources, peer-reviewed research, public data | Basis; check who funded/benefits |
| T3 | Reputable media and expert organisations summarising T1/T2 | Points to the original; trace it |
| T4 | Blogs, forums, social posts, marketing, AI-generated summaries | Signal only, never the basis |

**Vendor pages.** A company's own page is T1 for what the company itself offers or decides: its prices, plans, release dates, policies, documented behaviour. The same page is T4 for claims about quality, speed, benchmarks or competitors. Two pages from the same company count as one independent source.

## 3. SIFT for unfamiliar sources
1. **Stop** before trusting, especially if the claim is exciting.
2. **Investigate the source** by searching for it elsewhere (lateral reading), not by reading its own About page.
3. **Find better coverage**: often faster than judging a weak source.
4. **Trace** the claim, number or quote to its original and check the original says exactly that.

## 4. Counter-evidence (never skip)
For each new or changed main claim, run at least one search designed to find the opposite: `<X> rolled back`, `<X> not available in <region>`, `<X> delayed`, `<X> criticism`, `<X> false`. Record the query and outcome, including "none found". Ask: who benefits if this is true? Is a correlation being presented as a cause? Is the source talking about a different version, region or plan?

## 5. Confidence levels

| Level | Meaning | Typical basis |
|---|---|---|
| `high` | Very unlikely to be wrong as stated | `read` T1 source, current (within the topic's freshness window), no unresolved counter-evidence |
| `medium` | Probably right, could be off in detail | `read` T2/T3 sources, ≥ 2 independent, or T1 that is ambiguous/old |
| `low` | Could well be wrong | single source, stale, or only `search-snippet` support |
| `very-low` | Treat as rumour | T4 only, or sources contradict each other |

**Count independent sources.** Ten articles rewriting one press release are one source.

**Ceilings** (these override everything else):
- only `search-snippet` / `unverified` → at most `low`
- only T4 → at most `very-low`
- `high` requires at least one `read` T1 source

**Downgrade** when there is a real reason to doubt the claim, not merely a theoretical one: the source is indirect (different product tier, region, version), the sources disagree, the claim is vague, or the source has an interest in it being believed.

Write the reason in one line: `medium — official blog, read; pricing page not yet updated`.

## 6. Freshness windows (default `review_by`)

| Kind of claim | review_by |
|---|---|
| Prices, promotions, availability, rankings | 1 month |
| Software features, AI models, APIs | 3 months |
| Policy, law, terms of service | 6 months |
| Science, methodology, history | 12 months |

## 7. Writing
- Same strength as the source ("may" stays "may"; "announced" is not "shipped").
- Dates and versions on everything that can change.
- Separate **evidence says** from **interpretation**. Interpretation never gets a confidence above the evidence under it.
- When the run found nothing, say "No change" and list what was checked. A short honest digest beats a padded one.

## 8. Search by region and language
A search index reflects where it is built. A topic about a national regulator, a local bank or a law written in another language is poorly served by an English, US-centred index, and "I couldn't find it" from one engine is not evidence that it does not exist.
- Each topic declares `region` (ISO country code or `global`) and `languages`.
- If you can drive a browser, search the region's leading engine in the topic's language(s), plus English if the topic is international. The leading engine is not the same everywhere; check current shares at https://gs.statcounter.com/search-engine-market-share when unsure.
- If you only have a built-in search tool, use it, and note in the digest which tool was used and its known limits (some built-in tools state they are US-only).
- Before concluding "no coverage" or "nobody has done this", try at least two queries in the local engine and language.
- CAPTCHA, consent walls and bot checks: do not attempt to bypass them. Record the source as "Could not check (bot check)".

## Sources for this method
- Garritty C. et al. (2021) Cochrane Rapid Reviews Methods Group interim guidance. *J Clin Epidemiol* 130:13–22. https://pmc.ncbi.nlm.nih.gov/articles/PMC7557165/
- GRADE certainty criteria, CDC ACIP GRADE Handbook ch. 7. https://www.cdc.gov/acip-grade-handbook/hcp/chapter-7-grade-criteria-determining-certainty-of-evidence/index.html
- SIFT (Caulfield): https://writingcommons.org/section/information-literacy/information-evaluation/sift-stop-investigate-source-find-better-coverage-trace-claims/
- Analysis of Competing Hypotheses: https://en.wikipedia.org/wiki/Analysis_of_competing_hypotheses
- Oxford CEBM Levels of Evidence: https://www.cebm.ox.ac.uk/resources/levels-of-evidence/ocebm-levels-of-evidence
