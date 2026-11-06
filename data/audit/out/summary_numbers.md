| Group | Number | Published | Today's code+data | Fix A | Fix A+B |
|---|---|---|---|---|---|
| store | acts | 23 | 23 | 23 | 23 |
| store | versions | 406 | 406 | 406 | 406 |
| store | article versions | 3555 | 3555 | 3555 | 3555 |
| store | retroactive article versions (README 54) | 54 | 54 | 54 | 53 |
| store | overtaken pending article versions (README 4) | 4 | 4 | 4 | 5 |
| store | overlapping non-empty intervals (REPORT 0) | 0 | 0 | 0 | 0 |
| store | article versions not in force yet (pending) | — | 0 | 3 | 3 |
| store | versions starting later than the §13 default | — | 46 | 56 | 56 |
| retrieval (264 amount probes) | all versions, date ignored: R@1 | 0.239 (0.191–0.294) | 0.239 (0.191–0.294) | 0.239 (0.191–0.294) | 0.242 (0.195–0.298) |
| retrieval (264 amount probes) | all versions, date ignored: right article, wrong version @1 | 0.432 (0.373–0.492) | 0.432 (0.373–0.492) | 0.432 (0.373–0.492) | 0.428 (0.370–0.488) |
| retrieval (264 amount probes) | today's text only: R@1 | 0.117 (0.084–0.162) | 0.117 (0.084–0.162) | 0.117 (0.084–0.162) | 0.117 (0.084–0.162) |
| retrieval (264 amount probes) | today's text only: right article, wrong version @1 | 0.390 (0.333–0.450) | 0.390 (0.333–0.450) | 0.390 (0.333–0.450) | 0.390 (0.333–0.450) |
| retrieval (264 amount probes) | versions in force on the date: R@1 | 0.693 (0.635–0.746) | 0.697 (0.639–0.749) | 0.697 (0.639–0.749) | 0.693 (0.635–0.746) |
| retrieval (264 amount probes) | versions in force on the date: right article, wrong version @1 | 0.000 (0.000–0.014) | 0.000 (0.000–0.014) | 0.000 (0.000–0.014) | 0.000 (0.000–0.014) |
| reranker (1,207 probes) | bm25 (static): R@1 | 0.474 | 0.474 | 0.471 | 0.471 |
| reranker (1,207 probes) | bm25 (static): wrong version @1 | 0.198 | 0.198 | 0.200 | 0.200 |
| reranker (1,207 probes) | date filter → bm25: R@1 | 0.746 | 0.746 | 0.744 | 0.742 |
| reranker (1,207 probes) | date filter → bm25: wrong version @1 | 0.000 | 0.000 | 0.000 | 0.000 |
| reranker (1,207 probes) | zero-shot (static): R@1 | 0.537 | 0.537 | 0.538 | 0.532 |
| reranker (1,207 probes) | zero-shot (static): wrong version @1 | 0.155 | 0.155 | 0.154 | 0.160 |
| reranker (1,207 probes) | date filter → zero-shot: R@1 | 0.751 | 0.751 | 0.751 | 0.748 |
| reranker (1,207 probes) | date filter → zero-shot: wrong version @1 | 0.000 | 0.000 | 0.000 | 0.000 |
| reranker (1,207 probes) | fine-tuned/bm25 (static): R@1 | 0.671 | 0.671 | 0.672 | 0.665 |
| reranker (1,207 probes) | fine-tuned/bm25 (static): wrong version @1 | 0.067 | 0.067 | 0.065 | 0.071 |
| reranker (1,207 probes) | date filter → fine-tuned/bm25: R@1 | 0.747 | 0.747 | 0.745 | 0.742 |
| reranker (1,207 probes) | date filter → fine-tuned/bm25: wrong version @1 | 0.000 | 0.000 | 0.000 | 0.000 |
| reranker (1,207 probes) | fine-tuned/temporal (static): R@1 | 0.675 | 0.675 | 0.677 | 0.673 |
| reranker (1,207 probes) | fine-tuned/temporal (static): wrong version @1 | 0.060 | 0.060 | 0.059 | 0.063 |
| reranker (1,207 probes) | date filter → fine-tuned/temporal: R@1 | 0.748 | 0.748 | 0.748 | 0.746 |
| reranker (1,207 probes) | date filter → fine-tuned/temporal: wrong version @1 | 0.000 | 0.000 | 0.000 | 0.000 |
| reranker (1,207 probes) | fine-tuned/mixed (static): R@1 | 0.673 | 0.673 | 0.674 | 0.669 |
| reranker (1,207 probes) | fine-tuned/mixed (static): wrong version @1 | 0.072 | 0.072 | 0.070 | 0.075 |
| reranker (1,207 probes) | date filter → fine-tuned/mixed: R@1 | 0.751 | 0.751 | 0.750 | 0.747 |
| reranker (1,207 probes) | date filter → fine-tuned/mixed: wrong version @1 | 0.000 | 0.000 | 0.000 | 0.000 |
| reranker McNemar | fine-tuned/temporal (static) vs fine-tuned/bm25 (static) | 54 vs 49, p=0.6937 | 54 vs 49, p=0.6937 | 53 vs 47, p=0.6173 | 55 vs 46, p=0.4262 |
| reranker McNemar | fine-tuned/temporal (static) vs fine-tuned/mixed (static) | 44 vs 41, p=0.8284 | 44 vs 41, p=0.8284 | 43 vs 40, p=0.8264 | 44 vs 40, p=0.7436 |
| reranker McNemar | fine-tuned/bm25 (static) vs zero-shot (static) | 212 vs 50, p=0.0 | 212 vs 50, p=0.0 | 213 vs 51, p=0.0 | 213 vs 52, p=0.0 |
| reranker McNemar | date filter → fine-tuned/temporal vs date filter → bm25 | 23 vs 20, p=0.7608 | 23 vs 20, p=0.7608 | 24 vs 19, p=0.5424 | 24 vs 19, p=0.5424 |
| reranker McNemar | date filter → bm25 vs fine-tuned/temporal (static) | 104 vs 19, p=0.0 | 104 vs 19, p=0.0 | 101 vs 20, p=0.0 | 103 vs 20, p=0.0 |
| NL (105 questions) | year_ok | 1.000 (0.965–1.000) | 1.000 (0.965–1.000) | 1.000 (0.965–1.000) (no gold change) | 1.000 (0.965–1.000) |
| NL (105 questions) | r1 | 0.581 (0.485–0.671) | 0.581 (0.485–0.671) | 0.581 (0.485–0.671) | 0.581 (0.485–0.671) |
| NL (105 questions) | r5 | 0.800 (0.714–0.865) | 0.800 (0.714–0.865) | 0.800 (0.714–0.865) | 0.800 (0.714–0.865) |
| NL (105 questions) | amount_ok | 0.743 (0.652–0.817) | 0.743 (0.652–0.817) | 0.743 (0.652–0.817) (no gold change) | 0.724 (0.632–0.800) |
| NL (105 questions) | distractor | 0.038 (0.015–0.094) | 0.038 (0.015–0.094) | 0.038 (0.015–0.094) (no gold change) | 0.057 (0.026–0.119) |
| NL (105 questions) | insufficient | 0.181 (0.119–0.265) | 0.181 (0.119–0.265) | 0.181 (0.119–0.265) (no gold change) | 0.181 (0.119–0.265) |
| NL (105 questions) | wrong answers flagged by code | 1 of 11 | 1 of 11 | 1 of 11 | 3 of 13 |
| exposure | amount probes with a new gold label | — | 0 | 0 | 6 |
| exposure | rerank probes with a new gold label | — | 0 | 4 | 13 |
| exposure | NL questions with a new gold label | — | 0 | 0 | 3 |
| exposure | NL questions whose gold version's interval changes | — | 0 | 10 | 13 |
| exposure | NL questions with a retrieved source whose interval changes | — | 0 | 53 | 60 |
| exposure | P0 items whose reference version's interval changes | — | 0 | 33 | 45 |
| exposure | P0 items whose version in force on the item date changes | — | 0 | 0 | 6 |
| benchmark if regenerated | probes by type (version/span/amount/bitemporal) | 1225/2010/264/104 | 1225/2010/264/104 | 1224/2010/264/100 | 1223/2009/264/98 |
| benchmark if regenerated | temporal R@1 on regenerated amount probes | 0.693 | 0.697 | 0.697 | 0.697 |
