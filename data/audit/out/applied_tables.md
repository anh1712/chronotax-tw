| Group | Number | Before (pre-fix files / backup store) | After (repo now) | = audit A+B column? |
|---|---|---|---|---|
| store | acts | 23 | 23 | yes |
| store | versions | 406 | 406 | yes |
| store | article versions | 3555 | 3555 | yes |
| store | retroactive article versions | 54 | 53 | yes |
| store | overtaken pending article versions | 4 | 5 | yes |
| store | articles not in force yet (pending) | 0 | 3 | yes |
| store | overlapping non-empty intervals | 0 | 0 | yes |
| store | Income Tax Act §126 commencement rules | 20 | 21 |  |
| store | article versions with a new start date | 0 | 213 |  |
| retrieval, 264 amount probes | all versions, date ignored: R@1 | 0.239 (0.191–0.294) | 0.242 (0.195–0.298) | yes |
| retrieval, 264 amount probes | all versions, date ignored: R@5 | 0.644 | 0.64 |  |
| retrieval, 264 amount probes | all versions, date ignored: right article, wrong version @1 | 0.432 (0.373–0.492) | 0.428 (0.370–0.488) | yes |
| retrieval, 264 amount probes | today's text only: R@1 | 0.117 (0.084–0.162) | 0.117 (0.084–0.162) | yes |
| retrieval, 264 amount probes | today's text only: R@5 | 0.121 | 0.121 |  |
| retrieval, 264 amount probes | today's text only: right article, wrong version @1 | 0.390 (0.333–0.450) | 0.390 (0.333–0.450) | yes |
| retrieval, 264 amount probes | in force on the date: R@1 | 0.693 (0.635–0.746) | 0.693 (0.635–0.746) | yes |
| retrieval, 264 amount probes | in force on the date: R@5 | 0.788 | 0.784 |  |
| retrieval, 264 amount probes | in force on the date: right article, wrong version @1 | 0.000 (0.000–0.014) | 0.000 (0.000–0.014) | yes |
| reranker, 1,207 probes | bm25 (static): R@1 | 0.474 (0.446–0.502) | 0.471 (0.443–0.500) | yes |
| reranker, 1,207 probes | bm25 (static): wrong version @1 | 0.198 | 0.200 | yes |
| reranker, 1,207 probes | date filter → bm25: R@1 | 0.746 (0.720–0.769) | 0.742 (0.716–0.765) | yes |
| reranker, 1,207 probes | date filter → bm25: wrong version @1 | 0.000 | 0.000 | yes |
| reranker, 1,207 probes | zero-shot (static): R@1 | 0.537 (0.509–0.565) | 0.532 (0.504–0.560) | yes |
| reranker, 1,207 probes | zero-shot (static): wrong version @1 | 0.155 | 0.160 | yes |
| reranker, 1,207 probes | date filter → zero-shot: R@1 | 0.751 (0.726–0.775) | 0.748 (0.723–0.772) | yes |
| reranker, 1,207 probes | date filter → zero-shot: wrong version @1 | 0.000 | 0.000 | yes |
| reranker, 1,207 probes | fine-tuned/bm25 (static): R@1 | 0.671 (0.644–0.697) | 0.665 (0.638–0.691) | yes |
| reranker, 1,207 probes | fine-tuned/bm25 (static): wrong version @1 | 0.067 | 0.071 | yes |
| reranker, 1,207 probes | date filter → fine-tuned/bm25: R@1 | 0.747 (0.722–0.771) | 0.742 (0.717–0.766) | yes |
| reranker, 1,207 probes | date filter → fine-tuned/bm25: wrong version @1 | 0.000 | 0.000 | yes |
| reranker, 1,207 probes | fine-tuned/temporal (static): R@1 | 0.675 (0.648–0.701) | 0.673 (0.646–0.699) | yes |
| reranker, 1,207 probes | fine-tuned/temporal (static): wrong version @1 | 0.060 | 0.063 | yes |
| reranker, 1,207 probes | date filter → fine-tuned/temporal: R@1 | 0.748 (0.723–0.772) | 0.746 (0.720–0.769) | yes |
| reranker, 1,207 probes | date filter → fine-tuned/temporal: wrong version @1 | 0.000 | 0.000 | yes |
| reranker, 1,207 probes | fine-tuned/mixed (static): R@1 | 0.673 (0.646–0.699) | 0.669 (0.642–0.695) | yes |
| reranker, 1,207 probes | fine-tuned/mixed (static): wrong version @1 | 0.072 | 0.075 | yes |
| reranker, 1,207 probes | date filter → fine-tuned/mixed: R@1 | 0.751 (0.725–0.774) | 0.747 (0.722–0.771) | yes |
| reranker, 1,207 probes | date filter → fine-tuned/mixed: wrong version @1 | 0.000 | 0.000 | yes |
| reranker McNemar | fine-tuned/temporal (static) vs fine-tuned/bm25 (static) | 54 vs 49, p=0.6937 | 55 vs 46, p=0.4262 | yes |
| reranker McNemar | fine-tuned/temporal (static) vs fine-tuned/mixed (static) | 44 vs 41, p=0.8284 | 44 vs 40, p=0.7436 | yes |
| reranker McNemar | fine-tuned/bm25 (static) vs zero-shot (static) | 212 vs 50, p=0.0 | 213 vs 52, p=0.0 | yes |
| reranker McNemar | date filter → fine-tuned/temporal vs date filter → bm25 | 23 vs 20, p=0.7608 | 24 vs 19, p=0.5424 | yes |
| reranker McNemar | date filter → bm25 vs fine-tuned/temporal (static) | 104 vs 19, p=0.0 | 103 vs 20, p=0.0 | yes |
| NL, 105 questions | year_ok | 1.000 (0.965–1.000) | 1.000 (0.965–1.000) | yes |
| NL, 105 questions | r1 | 0.581 (0.485–0.671) | 0.581 (0.485–0.671) | yes |
| NL, 105 questions | r5 | 0.800 (0.714–0.865) | 0.800 (0.714–0.865) | yes |
| NL, 105 questions | amount_ok | 0.743 (0.652–0.817) | 0.724 (0.632–0.800) | yes |
| NL, 105 questions | distractor | 0.038 (0.015–0.094) | 0.057 (0.026–0.119) | yes |
| NL, 105 questions | all_verified | 0.676 (0.582–0.758) | 0.676 (0.582–0.758) |  |
| NL, 105 questions | insufficient | 0.181 (0.119–0.265) | 0.181 (0.119–0.265) | yes |
| NL, 105 questions | wrong answers flagged by code | 1 of 11 | 3 of 13 | yes |
| benchmark | probes by type | {"version_id": 1225, "span": 2010, "amount": 264, "bitemporal": 104} | {"version_id": 1225, "span": 2010, "amount": 264, "bitemporal": 104} |  |
| benchmark | probes with a new gold label (TW-TaxTime / reranker / NL rows) | — | 28 / 13 / 6 |  |
