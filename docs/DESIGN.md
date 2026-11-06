# ChronoTax — design

**One line:** a question-answering system that tells you what the tax law said *for the period you ask about*, cites the exact
article version, and checks its own answer — for Taiwan tax law (this repo).

*This is the original design plan (2026-10). The status column shows the plan at that time; measured results are in
the README and `docs/REPORT.md`.*

## Why this is a research problem, not a chatbot
- LLMs cite the wrong article or an outdated version of it. TW-LegalBench (ICAIL 2026) reports models "struggle to cite exact
  legal articles"; FiscalQA Pro (French tax code, 2026) shows static RAG finds the right *version* almost never.
- Tax law has three different clocks, and most systems model at most one:
  1. **valid time** — when a rule applies (Taiwan's 2026-09-11 amendment of Income Tax Act Art. 17 applies from 2026-01-01);
  2. **publication time** — when the public could know it (a question asked on 2026-06-01 could not know that amendment);
  3. **tax period** — income tax questions are about a tax year filed the following May, not a calendar date.
- Effective dates differ per article inside one amendment (Income Tax Act Art. 126), so "the amendment date" is wrong for
  some articles.

## Components
| # | Component | Method | Status |
|---|---|---|---|
| C1 | **Bitemporal legal store** | every article version has `[valid_from, valid_to)` and `published`; effective dates derived by explicit rules with a recorded basis (中央法規標準法 §13, "自…施行", per-article 施行 clauses) | v0: valid time, whole-amendment dates |
| C2 | **Period resolver** | maps a question to (tax period, knowledge date); rule-first, LLM fallback; asks back when the period is missing (two-branch answer) | planned |
| C3 | **Hybrid retrieval** | BM25 (FTS5 trigram, no segmenter needed for Chinese) + multilingual dense embeddings; candidates restricted to versions in force for the resolved period | v0: BM25 only |
| C4 | **Reranker with temporal hard negatives** | cross-encoder fine-tuned on (question, article-version) pairs; negatives include the *superseded version of the correct article* — only a versioned store can produce them. Ablation: random / BM25 / structural / temporal negatives | done: fine-tuning helps (p<0.001); temporal negatives = lexical negatives (p=0.69); symbolic filter wins (p<0.001) |
| C5 | **Cited answer + verification** | LLM writes claims each tagged with an article-version id; deterministic checks (amounts, dates, article ids must appear verbatim in the cited version) before an LLM verifier; measure verifier over-pruning | done: code checks (REPORT §4.3); LLM verifier in progress |
| C6 | **Evaluation** | rule-graded benchmark (article id + version + amount, no LLM judge needed), 3-layer metrics (retrieval recall of gold version → version accuracy → answer accuracy), oracle ablation (gold version injected), counterfactual temporal probes (same question, different periods) to measure recency bias; LLM-judge meta-evaluation (agreement, temporal bias) | planned |
| C7 | **Cross-domain transfer** | same pipeline, probe generator and retrieval code on 20 Taiwan health and medical acts | done: `docs/CHRONOMED.md` |
| C8 | **Bilingual demo + MCP** | zh-TW / English UI, official MOJ English text as gloss, timeline view of each article, MCP tools (`get_article(as_of)`, `history`, `verify_citations`) | planned |

## Data (Taiwan)
- Versions: LYAPI v2 (Legislative Yuan records, CC BY 4.0) — full text of every version of 23 tax-related acts.
- Dates: MOJ 法規沿革 (promulgation, effective clauses). Law texts are not copyrightable (著作權法 §9); MOJ data under OGDL-Taiwan 1.0 (CC BY 4.0 compatible).
- Next: enforcement rules (施行細則, MOJ current text only), MOF announcements of yearly exemption/deduction amounts, MOJ English versions.

## Evaluation targets (to be measured, not claimed)
- Retrieval: Recall@k of the gold *article version*; temporal misgrounding rate (right article, wrong version).
- Answer: rule-graded accuracy on a held-out set nobody tunes on; Wilson 95% CI; McNemar for A/B.
- Noise: run-to-run variance reported with every number.

## Working rules
Check whether the gold unit reaches the context before blaming the generator; audit gold labels (gold errors are
common); report judge disagreement; keep infrastructure errors separate from answer errors.
