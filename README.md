# ChronoTax-TW

**Point-in-time retrieval and question answering over Taiwan law: answer with the article version that applied on
the date asked, not today's text.**

> *"What was the standard deduction for tax year 2016?"* has a different answer from the same question for 2026, and
> both differ from the amount written in the Income Tax Act today. A retrieval index that ignores dates cites the
> right article in the wrong version.

Author: Nguyen The Anh (theanhnguyen050@gmail.com) · Technical report (draft): [docs/REPORT.md](docs/REPORT.md)

## Main findings

| | Finding | Evidence |
|---|---|---|
| 1 | An index that ignores dates returns the right tax article in the **wrong version for 43%** of amount probes; restricting the index to the law in force on the date gives **0%**. | 264 amount probes, Wilson 95% CI |
| 2 | Fine-tuning a cross-encoder with dates written into its inputs makes it much more time-aware (wrong version 16.0% → 6–7.5%, p < 0.001), but a **symbolic validity filter still beats the best fine-tuned reranker** (R@1 0.742 vs 0.673, p < 0.001). | 1,207 held-out probes, article-level split, paired McNemar |
| 3 | **Negative result:** superseded-version ("temporal") hard negatives are no better than lexical negatives (p = 0.43). An earlier small run suggested they were. | same 1,207 probes |
| 4 | The finding **transfers to health law** in direction: on 20 Taiwan health and medical acts, ignoring dates gives the wrong version for 29% (95% CI 21–38%) of amount probes; the filter gives 0% and raises R@1 from 0.22 to 0.585 (43 vs 0 discordant, p < 0.001). | [docs/CHRONOMED.md](docs/CHRONOMED.md) |
| 5 | **Correction, 2026-10-26:** porting to health law exposed two date-parsing bugs in the tax store. Both were fixed; all numbers here are the corrected ones; no conclusion or significance test changed. | [docs/AUDIT_DATES.md](docs/AUDIT_DATES.md) |

Design rule: **put time in the index (rules), not in the model.**

## What is in the store
- Every version (full text) of **23 tax-related acts: 406 versions, 3,555 article versions** from the Legislative
  Yuan open API (LYAPI v2), e.g. Income Tax Act: 73 versions since 1943; VAT Act: 45 versions since 1931.
- Promulgation and effective dates from the Ministry of Justice amendment history, each with the rule that produced
  it: per-article dates and Executive Yuan orders printed in the history, each act's own commencement article
  (Income Tax Act Art. 126 parsed into rules), tax-year and "N years after promulgation" forms, or the default of the
  Central Regulation Standard Act §13. Articles whose start date the Executive Yuan has not set yet are kept out of force.
- Three clocks: **valid time** (when a rule applies), **publication time** (when it could be known; 53 retroactive
  article versions), **tax year**. Bitemporal lookup: `known(article, valid_on, known_on)`.
- Overtaken pending amendments (5) are never applied; 0 overlapping validity intervals.
- Ministry of Finance announced amounts per tax year (`curated/`), because the Act's base amounts are adjusted by CPI.
- Full-text search restricted to the law in force on a date (SQLite FTS5 trigram tokenizer, no Chinese segmenter).

## Results

### Index design (TW-TaxTime v0, 264 amount probes, Wilson 95% CI)
| Index | R@1 gold version | Right article, wrong version @1 |
|---|---|---|
| static (all versions, date ignored) | 0.242 (0.195–0.298) | **0.428** (0.370–0.488) |
| latest (today's law only) | 0.117 (0.084–0.162) | 0.390 (0.333–0.450) |
| **temporal (law in force on the date)** | **0.693** (0.635–0.746) | **0.000** (0.000–0.014) |

Queries are cloze contexts taken from the law text (lexical), so absolute numbers overstate what natural questions
would get; the gap between indexes is the point.

### Can a model learn time, or do you need a date filter? (`src/rerank.py`)
Cross-encoder `BAAI/bge-reranker-base`, dates written into query and passage, fine-tuned on ~3,000 synthetic queries
from articles **disjoint** from the test articles. Test: 1,207 held-out probes (264 amount + 943 changed-wording);
candidates = static top-30 over all versions.

| System | R@1, no date filter | wrong version @1, no filter | R@1 with date filter |
|---|---|---|---|
| BM25 order | 0.471 (0.443–0.500) | 0.200 | 0.742 |
| zero-shot reranker | 0.532 (0.504–0.560) | 0.160 | 0.748 |
| fine-tuned, lexical negatives | 0.665 (0.638–0.691) | 0.071 | 0.742 |
| fine-tuned, temporal negatives (superseded versions) | **0.673** (0.646–0.699) | **0.063** | 0.746 |
| fine-tuned, mixed | 0.669 (0.642–0.695) | 0.075 | 0.747 |

Paired exact McNemar: fine-tuned vs zero-shot 213/52, p < 0.001; temporal vs lexical negatives 55/46, p = 0.43;
validity filter vs best learned 103/20, p < 0.001; reranking after the filter 24/19, p = 0.54.

### End to end on natural questions (105 LLM-paraphrased taxpayer questions, rule-based gold)
Period resolved correctly 100%; gold version retrieved @1 58% / @5 80%; correct amount stated 72%; wrong-version
amount stated 6%; abstained 18%. Code verification flagged 3 of 13 wrong answers; the other 10 were *grounded* in a
wrong article: grounding checks prevent fabrication, they do not prove applicability. Details: [docs/REPORT.md](docs/REPORT.md).

## Repository map
| Path | What |
|---|---|
| `src/` | store builder (`fetch_ly.py`, `moj_history.py`, `effect_rules.py`, `build_db.py`), benchmark (`bench.py`, `nl_bench.py`), retrieval and reranker experiments (`eval_retrieval.py`, `rerank.py`), answering with citations and code checks (`answer.py`), demo (`app.py` + `web/`), MCP server (`mcp_server.py`) |
| `src/med/` | ChronoMed-TW: the same pipeline on 20 health and medical acts (CPU only, no LLM) |
| `src/audit/` | the date audit: reader comparison, store variants, re-labelling, all published numbers |
| `data/bench/` | frozen probe files and result files (`results_*.json`); pre-fix files in `_prefix_2026-10-26/` |
| `data/med/` | health benchmark, results and figures |
| `data/audit/` | the two fixes as patches and every audit output |
| `docs/` | `REPORT.md` (technical report draft), `CHRONOMED.md`, `AUDIT_DATES.md`, `DESIGN.md` (original plan) |

The SQLite stores (`data/lawtw.db`, `data/med/medtw.db`) are not in git; rebuild them as below, or download them
from the [Releases](https://github.com/anh1712/chronotax-tw/releases) page.

## Reproduce
Python 3.12. The store and the retrieval experiments need only the standard library; the reranker needs a GPU
(`requirements.txt`).
```bash
python -I src/registry.py resolve   # map LY law ids to MOJ pcodes (cached)
python -I src/fetch_ly.py           # download all versions (re-runs only fetch what is missing)
python -I src/build_db.py           # build data/lawtw.db (per-article commencement, bitemporal)
python -I src/english.py            # attach official MOJ English text (current version)
python -I src/eval_retrieval.py     # static vs latest vs temporal retrieval on the frozen probes
python -I src/rerank.py             # reranker experiments (GPU)
python -I src/med/run_all.py        # ChronoMed-TW, end to end
python -I src/app.py                # demo UI at http://127.0.0.1:8017
python -I src/query.py article 01513 第十七條 2022-06-01
```
`src/bench.py` re-samples probe dates; the published results use the frozen probe files in `data/bench/`.
Answering (`src/answer.py`) calls any OpenAI-compatible endpoint set by `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.

## Limitations
- Amount and span probes are cloze-style and lexical; natural questions are LLM-generated and checked by rule, not
  yet by Taiwanese tax professionals.
- Enforcement rules (施行細則) and MOF interpretation letters are not in the store; LYAPI lacks some very old versions.
- The author does not read Chinese; gold labels are rule-based (article id + version + amount) and the official MOJ
  English text is used as a gloss. Review by Taiwanese readers is welcome.
- AI coding assistants were used to write much of the code; the design, experiments and analysis are the author's.
- Work in progress (not in this repository yet): real taxpayer questions, and LLM verifiers for grounded but
  inapplicable answers.

## Data access note
The amendment histories were read in October 2026 from the MOJ `LawHistory.aspx` pages, one request per act, for
this research. The site's `robots.txt` asks crawlers not to fetch those pages, so please do not re-run the history
fetchers at scale; use the prebuilt stores from the Releases page. Moving the fetchers to the MOJ open-data
downloads (which include the amendment history) is planned.

## Data and licence
Code: MIT (see `LICENSE`). Law texts are not subject to copyright in Taiwan (Copyright Act §9). Version data: LYAPI v2
(OpenFun, CC BY 4.0). Dates and English texts: Ministry of Justice Laws & Regulations Database; announced amounts:
Ministry of Finance (Open Government Data License, Taiwan 1.0). This is a research prototype, not tax advice.
