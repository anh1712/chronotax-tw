# Time in the Index, Not in the Model: Point-in-Time Question Answering over Evolving Taiwan Tax Law

*Technical report (draft) — Nguyen The Anh*

## Abstract
Tax rules change often, and a question about a past tax year must be answered with the rule that applied then.
Retrieval-augmented generation (RAG) over today's text, or over all versions with the date ignored, cites the right
article in the wrong version. We describe ChronoTax-TW, a point-in-time QA system over Taiwan tax law (23 tax acts,
406 versions, 3,555 article versions). The store models three
clocks — when a rule applies, when it was published, and the tax year — and four hard cases: per-article commencement,
retroactive amendments, pending amendments overtaken by later ones, and statutory base amounts overridden by annual
Ministry of Finance announcements. On TW-TaxTime, a rule-graded benchmark generated from the version history, an index
that ignores dates returns the right article in the wrong version for 43% of amount probes; a validity-filtered index
returns 0%. A cross-encoder fine-tuned with dates written into its inputs becomes markedly more time-aware (wrong
version 16.0% → 6–7.5%, p < 0.001), but superseded-version hard negatives are no better than lexical ones (p = 0.43),
and the symbolic validity filter still wins (p < 0.001). Our conclusion is a design rule: put time in the index.

> **Correction (2026-10-26).** When the system was ported to health law, the new history reader was also run on
> the tax histories. It disagreed with the tax store on 31 of 413 MOJ history entries. Checking them against the
> official texts found two date-parsing bugs:
> 1. The history reader applied the *last* date in an entry to the whole amendment, although it is often an exception
>    for a few articles. It also missed clauses split by line wraps, tax-year forms, "自公布後一年施行" and "定於…施行".
> 2. A commencement sentence naming two amendments gave a rule only for the second.
>
> After the fix, 213 of 3,555 article versions start on a different date and 3 articles are kept out of force. The
> benchmark probes are unchanged; their gold labels were re-derived from the corrected dates (28 of 3,603 probes,
> 13 of 1,207 reranker probes, 3 of 105 NL questions). The numbers below are the corrected ones. They differ from the
> first draft by at most 0.006 (NL amount rates by 2 points), and no conclusion or significance test changes. Method,
> verdicts per entry and the full old/new table: `docs/AUDIT_DATES.md`.

## 1. Problem
- A question such as "What was the standard deduction for tax year 2016?" has a different answer from the same question
  for 2026, and both differ from the amount written in the Act today.
- Three clocks: **valid time** (when a rule applies), **publication time** (when it could be known — retroactive
  amendments break the equality), **tax period** (income tax questions name a tax year, filed the following May).
- Prior work: FiscalQA Pro (French tax code, 2026) shows static RAG almost never retrieves the right version and that
  first-stage recall, not version selection, is the bottleneck; Grabmair et al. (ICAIL 2026) on German law show
  recency bias; TW-LegalBench (ICAIL 2026) finds models struggle to cite exact Taiwanese articles.

## 2. System
### 2.1 Store
- **Sources.** Every version (full text) of 23 tax-related acts from the Legislative Yuan open API (LYAPI v2, CC BY 4.0);
  promulgation and effective dates from the Ministry of Justice amendment history; official English text (MOJ).
- **Effective dates by rule**, each with its basis. The sources, in order of precedence:
  1. per-article dates named in the MOJ history entry, including the Executive Yuan orders printed there;
  2. per-article rules parsed from each act's cumulative commencement article (e.g. Income Tax Act Art. 126: 21 rules,
     0 unparsed sentences), including tax-year forms ("自一百零七年度施行");
  3. the amendment's own commencement clause (explicit date, tax year, "N years after promulgation");
  4. the default of the Central Regulation Standard Act §13 (third day counting the promulgation day).

  Articles delegated to the Executive Yuan with no order yet are kept out of force (3).
- **Intervals in effective order.** An amendment passed later can take effect earlier; versions are ordered by
  (effective date, publication date). A pending version overtaken by a later-published one that takes effect first is
  never applied (5 cases). Result: 0 overlapping non-empty intervals; 53 retroactive versions flagged.
- **Bitemporal lookup.** `known(article, valid_on, known_on)` returns the text a reader could have known on `known_on`:
  e.g. Income Tax Act Art. 17 for 2026-03-01 as known on 2026-06-01 is the December 2025 text; as known today it is the
  September 2026 amendment, retroactive to 2026-01-01.
- **Administrative layer.** The Act states base amounts that the Ministry of Finance adjusts by CPI (Art. 5-1) and
  announces per tax year: the Act says a standard deduction of NT$120,000; the amount for ROC 115 (2026) is NT$136,000.
  Announced amounts are loaded with their official source and passed to the model as citable sources.
- **Answering.** Period resolver (ROC/Gregorian years, "年度", "tax year"); retrieval restricted to versions in force
  (FTS5 trigram, idf-weighted coverage re-ranking; English questions via the official English text); LLM answer with
  claim-level citations through any OpenAI-compatible endpoint; code verification: citations must be retrieved sources,
  every amount and percentage must occur in the cited text, and a claim that states the Act's base amount when an
  announced amount applies is flagged.
- **Interfaces.** Web demo (version timeline, character-level diffs, retroactivity flags, "as known on" date, English
  gloss, ask box) and an MCP server (`get_article`, `article_history`, `search_law`, `find_sources`, `verify_claim`).

## 3. TW-TaxTime benchmark
Generated from the store with zero LLM calls and graded by rule: 1,225 version probes, 264 **amount** probes (an amount
that changed between versions, with the neighbouring version's amount as a temporal distractor), 2,010 **span** probes
(wording inserted or deleted between versions; the query contains the changed words), 104 **bitemporal** probes.
The probe files are frozen (`data/bench/`); after the 2026-10-26 date correction their gold labels were re-derived from
the corrected store (28 probes changed), without re-sampling.
A natural-language extension (TW-TaxTime-NL) has an LLM paraphrase amount probes into taxpayer questions; questions that
copy ≥ 8 consecutive characters of the law or omit the period are rejected; gold stays rule-based.

## 4. Experiments
### 4.1 Index design (264 amount probes)
| Index | R@1 gold version | right article, wrong version @1 |
|---|---|---|
| all versions, date ignored | 0.242 (0.195–0.298) | 0.428 (0.370–0.488) |
| today's text only | 0.117 (0.084–0.162) | 0.390 (0.333–0.450) |
| versions in force on the date | 0.693 (0.635–0.746) | 0.000 (0.000–0.014) |

(The first draft's 0.693 came from an earlier sample of probe dates. The frozen probe file gave 0.697 before the date
correction and gives 0.693 = 183/264 after it, a difference of one probe.)

### 4.2 Can a model learn time? (1,207 held-out probes, article-level split)
Cross-encoder `bge-reranker-base`; dates written into query and passage; ~3,000 training queries from articles disjoint
from test articles; candidates = top-30 over all versions.

| System | R@1, no date filter | wrong version @1 | R@1 with filter |
|---|---|---|---|
| BM25 | 0.471 | 0.200 | 0.742 |
| zero-shot reranker | 0.532 | 0.160 | 0.748 |
| fine-tuned, lexical negatives | 0.665 | 0.071 | 0.742 |
| fine-tuned, superseded-version negatives | 0.673 | 0.063 | 0.746 |
| fine-tuned, mixed | 0.669 | 0.075 | 0.747 |

Paired exact McNemar: fine-tuned vs zero-shot 213/52 discordant, p < 0.001; temporal vs lexical negatives 55/46,
p = 0.43; validity filter vs best learned 103/20, p < 0.001; rerank after the filter 24/19, p = 0.54.
An earlier run on 264 probes suggested temporal negatives helped; it did not survive 4.6× more data.

### 4.3 End-to-end on natural questions (TW-TaxTime-NL)
150 amount probes (dates ≥ 2000) were paraphrased by an LLM into taxpayer questions; 105 passed the leakage and
period filters. Each question went through the full system (period resolution → validity-filtered retrieval → LLM
answer with claim citations → code verification). 0 infrastructure errors.

| Metric | Rate (Wilson 95% CI) |
|---|---|
| period resolved to the right year | 1.000 (0.965–1.000) |
| gold article version retrieved @1 / @5 | 0.581 (0.485–0.671) / 0.800 (0.714–0.865) |
| correct amount stated | 0.724 (0.632–0.800) |
| temporal distractor (neighbouring version's amount) stated | 0.057 (0.026–0.119) |
| answered "insufficient sources" | 0.181 (0.119–0.265) |
| wrong answers flagged by code verification | 3 of 13 |

After the date correction, 3 questions about the Income Tax Act Art. 5 brackets in 2009 changed gold: the 2009
amendment of Art. 5 applies only from tax year 2010. Their gold amount and temporal distractor swap. The answers were
not regenerated; the stored grades of these 3 questions were re-derived (`data/bench/results_nl.json`).

Reading: time is no longer the main failure — the period is always resolved and the wrong-version amount appears in
only 6% of answers; the remaining errors are retrieval (gold version outside the top 5 in 20%) and abstention.
Code verification rarely catches the wrong answers that remain, because they are *grounded*: the stated amount
does occur in a retrieved (but wrong) article. Grounding checks prevent fabrication; they do not prove relevance.

## 5. Discussion
- **Time belongs in the index.** Learned time-awareness is real but partial; a rule-based validity filter is exact for
  every probe whose period is known, and it is cheap. The remaining errors are wrong-article retrieval, the classic RAG
  problem, which a reranker can address once the date is fixed.
- **Grounded is not the same as applicable.** Code verification confirms that a number appears in the cited text; it
  cannot tell whether that text is the one that applies. The Act's base amount is grounded and wrong for the tax year;
  a second, administrative source layer and an explicit applicability check are needed.
- **Negative results matter.** The superseded-version-negative idea looked promising on a small sample and failed on a
  larger one; reporting it prevents others from over-investing.

## 6. Limitations
- Amount/span probes are cloze-style and lexical; natural questions are generated by an LLM and reviewed by rule, not
  yet by Taiwanese tax professionals. Announced MOF amounts are loaded only for the years verified from official pages.
- Enforcement rules (施行細則) and MOF interpretation letters are not yet in the Taiwan store; LYAPI lacks some very old
  versions (Amusement Tax Act: 6 of 15). The author does not read Chinese; Taiwanese review of the NL set is planned.
- AI coding assistants were used to write much of the code; the design, experiments and analysis are the author's.

## Data and code
Repository: https://github.com/anh1712/chronotax-tw. Law texts are not copyrightable in Taiwan (Copyright Act §9); LYAPI data CC BY 4.0; MOJ and
MOF data under the Open Government Data License (Taiwan) 1.0.
