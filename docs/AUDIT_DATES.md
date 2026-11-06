# Date audit of the ChronoTax-TW tax store

> **Status:** both fixes (A and B) were applied to `src/` on 2026-10-26; the store and all result files were
> rebuilt, and the README and REPORT give the corrected numbers. The text below describes the audit as run before that.

*Audit report, 2026-10-26. 0 LLM calls. `data/lawtw.db` was never opened or changed: all work used a
byte copy (`data/audit/lawtw_current_copy.db`, sha256 `dea6ed16d5948fd0…`, identical to the original).
Every number below comes from a file in `data/audit/out/` (named in each section).*

## 1. Question
The ChronoTax-TW store (`data/lawtw.db`: 23 tax acts, 406 versions, 3,555 article versions) takes each amendment's
effective date from the Ministry of Justice (MOJ) amendment history. Agent P3 wrote a new history reader for health
law (`src/med/moj_med.py`). On the 23 tax histories it gives a different amendment date for 31 of 413 entries.
1. Which reading is right for each of the 31 entries, and why do they differ?
2. How many article versions in today's store have a wrong validity interval?
3. Does any published number change (README, REPORT, application documents)?
4. Why does a re-run give temporal R@1 0.697 when README/REPORT say 0.693?

## 2. Why it matters
Every gold label in TW-TaxTime is computed from the store's own dates. A wrong date in the store is therefore
invisible to the benchmark: the index and the gold label share the same error. The only way to find such errors is to
read the official texts. The applicant will be asked about every number, so each one must be correct and explainable.

## 3. Data
- **MOJ amendment histories** of the 23 acts: cached pages `data/raw/moj/<pcode>-history.html` (fetched 2026-10-19,
  read-only). One live re-fetch (所得稅法, G0340003, 2026-10-26, `data/audit/raw/moj_live/`) is identical to the
  cache apart from visitor counters.
- **Each act's own commencement article** (施行條文, e.g. 所得稅法 §126) in the latest Legislative Yuan text
  (`data/raw/ly`). This is the statute itself, so it is a second official reading.
- **Official web pages** for three open points (`data/audit/out/sources.json`, S1–S5): two local tax-bureau notices for
  納稅者權利保護法, the MOJ "not yet in force" notices, and the MOF tax portal for 房屋稅條例.
- **Benchmarks** (read-only): `data/bench/tw_taxtime_v0.jsonl` (3,603 probes), `rerank_test.jsonl` (1,207 probes),
  `tw_taxtime_nl.jsonl` + `results_nl.json` (105 questions), and P0's `data/verifier/items.jsonl` (861 items).

## 4. Method
1. **Reproduce.** Both readers run unchanged on the 23 cached pages. Entries are paired by entry number and, as P3
   did, by position (`src/audit/compare_readers.py` → `out/reader_diff.json`).
2. **Decide each entry** by reading the official text (H = the MOJ history entry, S = the act's commencement article,
   W = an official web page). These are the rules the code applies:
   - An explicit date ("自/於/定於…施行") applies to the articles named just before it. If no article is named, it
     applies to the whole amendment.
   - "自公布日施行", or no date at all, means 中央法規標準法 §13: the third day counting the promulgation day
     (promulgation + 2 days, as in `moj_history.py`).
   - A tax-year form "自一百零七年度施行" means 1 January of that year. This is the store's own convention (`effect_rules.py`).
   - "自公布後一年施行" means the same calendar day one year later. Official tax-bureau pages confirm this:
     公布 105-12-28 → 施行 106-12-28 (S1, S2).
   - An Executive Yuan order printed in the entry dates the articles it names.
   - Verdict labels: **original** = the original reader's amendment date matches the official text; **new** = P3's
     reader matches it; **split** = each reader is right for some articles and wrong for others.
3. **Corrected store (Fix A).** I copied `moj_history.py` and `build_db.py` into `src/audit/patched/` and changed them
   (patch: `data/audit/fix_moj_history.patch`). Then I built `data/audit/lawtw_fixed.db` from the cached files only
   (`src/audit/build_variants.py fixed`). The reader works on whitespace-free text, gives every clause a scope
   (named articles, paragraph only, or whole amendment), reads the forms above, and no longer applies the last date in
   an entry to the whole amendment. The build gives each article its date in this order:
   1. an article named by the history entry or one of its orders;
   2. the act's commencement article (unchanged `effect_rules`);
   3. not in force yet (`pending`), for a new article of a delegated amendment that no order names, or an article the
      entry says is delegated with no order;
   4. the amendment's main date.

   A range such as "第4～7條" covers the 之-articles inside it.
4. **Determinism check.** I rebuilt the store with the unchanged code (`build_variants.py original`). It equals today's
   `lawtw.db` row for row: 406 versions and 3,662 article-version rows with the same ids, 0 differences
   (`out/cmp_current_vs_rebuilt.json`). Today's store therefore matches today's code. The corrected store keeps
   every id and text; only dates and bases change (`out/cmp_current_vs_fixed.json`).
5. **Fix B (separate, optional).** The audit found one more bug, in `effect_rules.py`. A commencement sentence that
   names two amendments gets a rule only for the last one (§5.4). Fix B (`data/audit/fix_effect_rules.patch`) is
   built on top of Fix A as `data/audit/lawtw_fixed_ab.db`.
6. **Impact.** I re-ran the original evaluation code unchanged, on today's store and on each corrected store:
   - `eval_retrieval.run` one probe at a time, for paired tests;
   - `rerank.metrics`, `in_force`, `passage`, `score` and `mcnemar`, with GPU fp16 as published;
   - `answer.retrieve`, without the LLM.

   On a corrected store, each probe's gold label is re-derived: the article version in force on the probe's date in
   that store. The probe itself stays the same. I report Wilson 95% intervals and exact McNemar tests.

## 5. Results

### 5.1 Reproduction
The two readers see the same 413 entries, with the same numbers and promulgation dates. **31 entries differ**, by entry
number and by P3's positional pairing alike. Each of the 31 maps to an LY version (`out/reader_diff.json`).

### 5.2 Verdicts and root causes
Verdict counts: **new reader right 23, original reader right 6, split 2 (both partly wrong), unclear 0** at entry level
(`out/verdicts.json`). Primary root cause of each difference:

| Code | Root cause | Entries |
|---|---|---|
| A | MOJ wraps lines inside words ("自 九十年", "施 行", "定自 一 百年"), and the original regex needs the clause unbroken | 8 (D02, D06, D07, D10, D18, D23, D25, D30) |
| B | Original takes the LAST date in the entry for the whole amendment, but that date is an exception for a few articles or paragraphs, or a second Executive Yuan order | 9 (D01, D03, D05, D09, D11, D17, D19, D22, D24) |
| C | Tax-year form "自…年度施行" not read by the original | 2 (D04, D12; also in D06, D08) |
| D | Relative date "自公布後一年施行" not read by the original | 2 (D20, D21) |
| E | "定於…施行" (於, not 自) not read by the original | 2 (D14, D15) |
| F | New reader leaves the amendment undated when the Executive Yuan orders name its articles (original right) | 6 (D13, D16, D26–D29) |
| G | Articles delegated to the Executive Yuan that never got an order (not in force) | 2 (D08, D31; D31 also has an application period, 施行期間, that neither reader reads) |

Six sub-points should be confirmed by a Chinese-reading person: D22 (does "第4～7條" include Art. 6-1?), the dates
of the commencement article itself in D08 (§126) and D26–D28 (§37), and the deletion date of Art. 5 in D26. None of
them changes an amount-bearing article except possibly D22 Art. 6-1, which also has support from the official tax
portal (S5).

The full table (H = MOJ history, S = commencement article, W = web source; last column = article versions whose start
date changes in the corrected store):

| D | Act, MOJ entry (promulgated) | LY version | Original reader | New (P3) reader | Verdict | Cause | Official reading | Evidence | Article versions re-dated |
|---|---|---|---|---|---|---|---|---|---|
| D01 | 所得稅法 #28 (1993-02-05) | 1993-01-18-修正 | 1993-01-01 (explicit) | 1993-02-07 (default_§13) | **new** | B | Arts 5-1, 17 from 1993-01-01; Art.126 by §13 (1993-02-07) | H | 1 |
| D02 | 所得稅法 #35 (2001-06-13) | 2001-05-29-修正 | 2001-06-15 (default_§13) | 2001-07-01 (explicit) | **new** | A | whole amendment 2001-07-01 | H; S (date delegated to Executive Yuan) | 12 |
| D03 | 所得稅法 #43 (2008-01-02) | 2007-12-14-修正 | 2008-01-01 (explicit) | 2008-01-04 (default_§13) | **new** | B | main §13 2008-01-04; only Art.14 ¶1 cat.9 from 2008-01-01 | H; S §126 | 2 |
| D04 | 所得稅法 #48 (2010-06-15) | 2010-05-28-修正 | 2010-06-17 (default_§13) | 2010-01-01 (tax_year) | **split** | C | Art.5 ¶5 from tax year 2010 (new reader); Art.126 by §13 2010-06-17 (original) | H; S §126 | 0 |
| D05 | 所得稅法 #49 (2011-01-19) | 2011-01-07-修正 | 2012-01-01 (explicit) | 2011-01-21 (default_§13) | **new** | B | main §13 2011-01-21; Arts 4 ¶1 items 1-2 and 17 ¶1(1)4 from 2012-01-01 (these items are the only changes in Arts 4 and 17, checked by text diff) | H; S §126 | 1 |
| D06 | 所得稅法 #57 (2014-06-04) | 2014-05-16-修正 | 2014-06-06 (default_§13) | 2015-01-01 (tax_year) | **new** | A+C | Arts 66-4, 66-6, 73-2 from 2015-01-01; rest from tax year 2015 | H; S §126 | 0 |
| D07 | 所得稅法 #60 (2015-06-24) | 2015-06-05-修正 | 2015-06-26 (default_§13) | 2016-01-01 (explicit) | **new** | A | 2016-01-01 | H; S §126 | 0 |
| D08 | 所得稅法 #62 (2016-07-27) | 2016-07-12-修正 | 2016-08-01 (explicit) | — (pending_executive_yuan) | **new** | G+C | Art.17-4 2016-08-01; Art.43-3 from tax year 2023; Art.43-4 not in force — *check: date of the amended Art.126 itself* | H; W S3 (MOJ notice) | 2 |
| D09 | 所得稅法 #64 (2018-02-07) | 2018-01-18-修正 | 2019-01-01 (explicit) | 2018-01-01 (explicit) | **new** | B | main 2018-01-01; 7 articles tax year 2018; Art.73-2 2019-01-01 | H; S §126 | 0 |
| D10 | 所得稅法 #65 (2019-07-24) | 2019-07-01-修正 | 2019-07-26 (default_§13) | 2019-01-01 (explicit) | **new** | A | 2019-01-01 | H; S §126 | 0 |
| D11 | 所得基本稅額條例 #1 (2005-12-28) | 2005-12-09-制定 | 2010-01-01 (explicit) | 2006-01-01 (explicit) | **new** | B | 2006-01-01; Art.15 2007-01-01; Art.12 ¶1 item 1 2010-01-01 (paragraph) | H; S §18 | 18 |
| D12 | 所得基本稅額條例 #2 (2012-08-08) | 2012-07-25-修正 | 2012-08-10 (default_§13) | 2013-01-01 (tax_year) | **new** | C | tax year 2013 | H; S §18 | 0 |
| D13 | 加值型及非加值型營業稅法 #21 (1997-05-07) | 1997-04-15-修正 | 2002-01-01 (explicit) | — (pending_executive_yuan) | **original** | F | Arts 16, 20 from 2002-01-01 (every amended article) | H | 0 |
| D14 | 加值型及非加值型營業稅法 #23 (1997-10-29) | 1997-10-09-修正 | 1997-10-31 (default_§13) | 1997-12-01 (executive_yuan_order) | **new** | E | Art.8 from 1997-12-01 (Executive Yuan order) | H; S §60 | 1 |
| D15 | 加值型及非加值型營業稅法 #24 (1998-06-17) | 1998-05-28-修正 | 1998-06-19 (default_§13) | 1998-07-10 (executive_yuan_order) | **new** | E | Art.53-1 from 1998-07-10 (Executive Yuan order) | H; S §60 | 1 |
| D16 | 加值型及非加值型營業稅法 #28 (2003-06-25) | 2003-06-05-修正 | 2003-07-01 (explicit) | 2003-06-27 (default_§13) | **original** | F | Art.11 from 2003-07-01 (the only amended article) | H | 0 |
| D17 | 加值型及非加值型營業稅法 #36 (2011-01-26) | 2011-01-10-修正 | 2011-09-01 (explicit) | — (pending_executive_yuan) | **new** | B | 18 articles 2011-04-01; Arts 16, 20 2011-09-01 (two orders) | H | 18 |
| D18 | 稅捐稽徵法 #19 (2011-05-11) | 2011-04-26-修正 | 2011-05-13 (default_§13) | 2011-07-01 (executive_yuan_order) | **new** | A | 2011-07-01 (Executive Yuan order) | H; S §51 | 3 |
| D19 | 稅捐稽徵法 #31 (2021-12-17) | 2021-11-30-修正 | 2022-01-01 (explicit) | 2021-12-19 (default_§13) | **new** | B | main §13 2021-12-19; Art.20 2022-01-01 | H; S §51 | 26 |
| D20 | 納稅者權利保護法 #1 (2016-12-28) | 2016-12-09-制定 | 2016-12-30 (default_§13) | 2017-12-28 (relative_after_promulgation) | **new** | D | one year after promulgation: 2017-12-28 | H; S §23; W S1, S2 | 23 |
| D21 | 納稅者權利保護法 #2 (2025-05-28) | 2025-05-09-修正 | 2025-05-30 (default_§13) | 2026-05-28 (relative_after_promulgation) | **new** | D | 2026-05-28 | H; W S2 | 3 |
| D22 | 房屋稅條例 #18 (2024-01-03) | 2023-12-19-修正 | 2024-07-01 (explicit) | 2024-01-05 (default_§13) | **new** | B | main §13 2024-01-05; Arts 4–7 (incl. 6-1), 12, 15 from 2024-07-01 — *check: whether 第4～7條 covers Art.6-1 (official portal says the 6-1 rule applies from 2024-07)* | H; S §25; W S5 (6-1) | 5 |
| D23 | 契稅條例 #11 (2001-06-13) | 2001-05-29-修正 | 2001-06-15 (default_§13) | 2001-07-01 (explicit) | **new** | A | 2001-07-01 | H; S §33 (delegated) | 3 |
| D24 | 使用牌照稅法 #20 (2014-06-18) | 2014-05-30-修正 | 2015-01-01 (explicit) | 2014-06-20 (default_§13) | **new** | B | main §13 2014-06-20; Art.7 2015-01-01 | H; S §38 | 3 |
| D25 | 貨物稅條例 #20 (1990-01-24) | 1990-01-18-全文修正 | — (by_executive_yuan_unknown) | 1990-06-01 (executive_yuan_order) | **new** | A | Arts 1–12 §13 1990-01-26; rest 1990-06-01 (Executive Yuan letter) | H | 37 |
| D26 | 貨物稅條例 #23 (1997-05-07) | 1997-04-15-修正 | 2002-01-01 (explicit) | — (pending_executive_yuan) | **original** | F | Arts 3, 13–15, 17, 18, 32 from 2002-01-01 (new reader also misreads 第13條至15條) — *check: dates of Art.37 itself and of the deletion of Art.5 (not named in the order)* | H; S §37 | 0 |
| D27 | 貨物稅條例 #25 (2001-10-31) | 2001-10-11-修正 | 2002-01-01 (explicit) | — (pending_executive_yuan) | **original** | F | Art.12 from 2002-01-01 — *check: date of Art.37 itself* | H; S §37 | 0 |
| D28 | 貨物稅條例 #47 (2025-08-19) | 2025-08-05-修正 | 2026-01-01 (explicit) | — (pending_executive_yuan) | **original** | F | Arts 8, 11 from 2026-01-01 — *check: date of Art.37 itself* | H; S §37 | 0 |
| D29 | 菸酒稅法 #6 (2009-05-13) | 2009-04-28-修正 | 2009-06-01 (explicit) | — (pending_executive_yuan) | **original** | F | Art.8 from 2009-06-01 (the only amended article) | H | 0 |
| D30 | 特種貨物及勞務稅條例 #1 (2011-05-04) | 2011-04-15-制定 | — (by_executive_yuan_unknown) | 2011-06-01 (executive_yuan_order) | **new** | A | 2011-06-01 (Executive Yuan order) | H; S §26 | 26 |
| D31 | 產業創新條例 #11 (2025-05-07) | 2025-04-18-修正 | — (by_executive_yuan_unknown) | 2025-05-09 (default_§13) | **split** | G+H | main §13 2025-05-09 (new reader right); Arts 22, 67-3 not in force (new reader right); Art.23-2 applies from 2025-01-01 (both readers wrong) | H; S §72; W S4 | 9 |

### 5.3 What today's store really gets wrong
At article level, only **19 of the 31 entries** change any date (**194 article versions**,
`out/change_groups.json`). The other 12 change nothing:
- in 6, the original reading was right (D13, D16, D26–D29);
- in 6, the act's own commencement article already gives the right per-article dates (D04, D06, D07, D09, D10, D12),
  for example 所得稅法 §126 for 2014, 2015, 2018 and 2019. In D04 this holds for the substantive Art. 5; the
  amendment's own §126 text is dated to tax year 2010 instead of §13, and only Fix B corrects that (§5.4).

The largest errors in today's store:

| Entry | Today's store | Official reading | Article versions |
|---|---|---|---|
| D11 所得基本稅額條例 2005 | whole act from 2010-01-01 | 2006-01-01 (Art. 15 2007-01-01); statute §18 says so | 18 (4 years late) |
| D20/D21 納稅者權利保護法 | 2016-12-30 / 2025-05-30 | 2017-12-28 / 2026-05-28 (one year after promulgation, S1/S2) | 23 + 3 (a year early) |
| D25 貨物稅條例 1990 | 1990-01-24 (promulgation) | Arts 1–12 1990-01-26, rest 1990-06-01 | 37 |
| D19 稅捐稽徵法 2021 | 2022-01-01 | 2021-12-19 except Art. 20 | 26 |
| D30 特種貨物及勞務稅條例 2011 | 2011-05-04 | 2011-06-01 (Executive Yuan order) | 26 |
| D17 營業稅法 2011 | 2011-09-01 | 18 articles 2011-04-01, Arts 16/20 2011-09-01 | 18 (5 months late) |
| D08 所得稅法 2016 | Arts 43-3, 43-4 from 2016-08-01 | 43-3 from tax year 2023; 43-4 not in force (MOJ notice, S3) | 2 |
| D31 產業創新條例 2025 | 2025-05-07 | 2025-05-09; Arts 22, 67-3 not in force (S4); Art. 23-2 from 2025-01-01 | 9 |

**P3's reader alone would not be a safe fix.** It leaves Arts 14 and 15 of 貨物稅條例 1997 "pending", because it
cannot read "第13條至15條". It leaves 房屋稅條例 Art. 6-1 out of the range "第4～7條". It gives no date at all to six
amendments whose articles are all dated by Executive Yuan orders. It also keeps the main date for paragraph-level
exceptions. Two things in today's store depend on the per-article layer:
- `effect_rules` reads "第四條至第七條" as Arts 4 and 7 only, so 房屋稅條例 Arts 5 and 6 rely on the version date.
- 所得稅法 Arts 4 and 17 (2011) are right only because of the §126 rule. For them, the excepted items are the only
  textual change (text diff checked).

**Nine more entries outside the 31** have date errors that neither the original nor P3's version date shows. The two
readers' amendment dates agree there, or both readers miss an order. 17 article versions are affected, and each was
checked against the history text, plus the statute where it has a matching sentence:
- 營業稅法 1995 (Arts 8, 51 → 1995-09-01, order without a number), 1997-05 (Art. 52 → 1997-07-01) and 1999 (Arts 11,
  21 → 1999-07-01, statute §60);
- 印花稅法 1986 (4 articles → 1986-04-01, order without a number);
- 證券交易稅條例 2023 (Arts 2-3, 3 → 2023-11-10, "自公布後六個月施行");
- 產業創新條例 2010, 2019, 2023 (retroactive application periods, statute §72) and 2026 (Art. 19-1 → 2027-01-01,
  MOJ notice).

Under Fix A, **211 article versions** get a new start date, 3 become "not in force yet", and 96 more get a new end date
(`out/cmp_current_vs_fixed.json`). There are no conflicts between history rules and commencement-article rules
(`history_rule` table, kind `conflict`: 0 rows).

### 5.4 Fix B: one sentence in 所得稅法 §126
所得稅法 §126 says: "九十八年五月二十七日修正公布之第五條第二項及九十九年六月十五日修正公布之同條第五項，自九十九年度施行".
`effect_rules` keeps only the last amendment date, so the rule for the 2009 amendment is lost. The MOJ history entry
(#47) says the same thing: "但第5條第2項及第5項規定，自九十九年度施行". A text diff shows that the substantive 2009 changes
to Art. 5 are ¶2 (income brackets and rates) and ¶5 (company tax); the rest is wording ("如左" → "如下", one
cross-reference). Today's store applies the 2009 Art. 5 text from
2009-05-29, although its changed paragraphs apply only from tax year 2010. This is the same situation as Arts 4/17 in
2011, which the store already handles.

Fix B gives one rule per amendment date, with "同條" meaning the article named just before. Only this one sentence in
the 23 commencement articles is affected. Fix B changes 4 article versions: the 2009 Art. 5 text becomes overtaken by
the 2010 text, and §126 of 2010 goes back to its §13 date (`out/cmp_fixed_vs_fixed_ab.json`). It matters because
**6 of the 264 amount probes** are on Art. 5 in 2009-05-29…2009-12-31. Their gold label moves to the 1991 text, whose
amount is exactly each probe's "temporal distractor". So under Fix B, gold and distractor swap for these 6 probes.
Caution: these are the Act's statutory base amounts. The amounts actually applied for tax year 2009 were adjusted by MOF
announcements, which are not in the store for that year (**UNVERIFIED**). The rule-based gold follows the
benchmark's own definition: the amount in the text in force.

**Not fixed, still open:**
- 所得稅法 has 2 LY versions that MOJ promulgated together with the previous bill (2000-12-28, 2007-06-15). They are
  dated by the LY passage date. Entry #34 says Art. 17 applies from 2000-01-01, but the store starts that text on
  2000-12-28. 1 amount probe and 1 version probe fall in that window (`out/leftovers.json`).
- 使用牌照稅法 2017: "第6條附表五規定，自修正公布日之次年一月一日施行" is a paragraph-level exception in a form
  neither reader parses.
- End dates of application periods (施行期間…止) are not modelled.

### 5.5 Store-level counts and every published number
"Today" means today's code and data (the store and probe files in `data/`). "Fix A" and "Fix A+B" use the same probe
files, with gold re-derived from the corrected store. The last two rows show what `bench.py` would generate if it were
re-run on the corrected store.

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

*Sources:*
- store: `out/store_stats.json`, `out/store_stats_ab.json`;
- 264 amount probes: `out/eval_amount.json`, `out/eval_amount_ab.json`;
- reranker: `out/rerank_filter.json`, `out/rerank_filter_ab.json`;
- NL: `out/nl_and_items.json`, `out/nl_and_items_ab.json`, `out/nl_regrade_ab.json`;
- regenerated benchmark: `out/regen_eval.json`, `out/regen_ab_eval.json`;
- all rows: `out/summary_numbers.json`.

Reading the table:
- **Store counts.** Versions (406), article versions (3,555) and acts (23) do not change, because the fix changes dates
  only. Retroactive article versions stay at 54 under Fix A, though 3 leave and 3 join the set; under A+B they are 53.
  Overtaken versions: 4 under A, 5 under A+B.
- **264 amount probes.** Fix A changes no gold label and no outcome. None of the 264 probe dates falls inside a moved
  window, although 32 probes sit on articles whose intervals changed (`out/probe_exposure.json`). Under A+B, temporal
  R@1 goes 0.697 → 0.693: 184 → 183 of 264, McNemar 0 vs 1, p = 1.0, the one probe being tt-amount-00727. Static R@1
  goes 0.239 → 0.242 and its wrong-version rate 0.432 → 0.428, so "43%" still holds.
- **Today's store graded with A+B labels.** Temporal R@1 is 0.682 (0.623–0.735) and the temporal index answers 4 probes
  (1.5%, 95% CI 0.6–3.8%) with the wrong version (`eval_amount_ab.json`, run `current/gold_fixed`). The published
  "0.000 wrong version" holds only relative to the store's own dates.
- **Reranker, 1,207 probes.** `rerank.score` on today's inputs reproduces every published R@1, every wrong-version rate
  and every McNemar count exactly.
  - Fix A changes 4 gold labels: 所得稅法 §126 (D05) and three span probes on 產業創新條例 Art. 22, whose 2025 text is
    not in force.
  - A+B changes 13. Model scores also change for probes whose candidates show changed dates in the passage text.
  - Every system moves by at most 0.006, and no change on the same system is significant under Fix A (all p ≥ 0.25).
    Under A+B, date filter → fine-tuned/bm25 drops 0 vs 6 (p = 0.03). Four of the 6 are relabelled probes. The other
    2 (tt-amount-02235, tt-span-00210) lose because the dates written into the candidate passages changed, which
    changes the model's scores (`rerank_filter_ab.json` → `models.changed_probes`).
  - Findings 1–3 of the README stay true:
    - fine-tuned vs zero-shot: 213 vs 51 (A) or 213 vs 52 (A+B), p < 0.001;
    - temporal vs lexical negatives: p = 0.62 (A) or 0.43 (A+B);
    - date filter vs best learned model: 0.744 vs 0.677, 101 vs 20 (A) or 0.742 vs 0.673, 103 vs 20 (A+B), p < 0.001;
    - reranking after the filter: p = 0.54.
- **NL, 105 questions.** `answer.retrieve` reproduces R@1/R@5 on today's store for 105/105 questions. Fix A changes no
  NL gold label and no R@1/R@5 (13 questions get a different source list, with the same hits). Under A+B, 3 questions
  change gold (Art. 5, 2009). Their stored grades can be re-derived exactly without the LLM, because gold and
  distractor swap: correct amount goes 0.743 → 0.724, wrong-version amount 0.038 → 0.057, and code verification
  flags 3 of 13 wrong answers instead of 1 of 11. Period resolution, R@1/R@5 and abstention are unchanged. Two caveats:
  - The answers were not re-generated (0 LLM calls).
  - 53 (A) or 60 (A+B) questions retrieved at least one source whose validity dates, shown to the LLM in the prompt,
    change. Their answers could differ if re-run.
- **P0 verifier items (861).** 33 (A) or 45 (A+B) items cite a version whose displayed validity interval changes. Only
  6 items (A+B: S-tt-amount-00733-A/B/D, S-tt-amount-00735-A/B/D) have a different version in force on their date.
  Fix A changes none (`out/nl_and_items*.json`).

### 5.6 Why 0.693 (published) vs 0.697 (re-run)
- **The data and the store are not the cause.** The store rebuilt with today's code equals today's `lawtw.db` (§4).
  Neither the "overtaken" change in `build_db.py` (commit d652f40) nor the regulation rows that `regulations.py`
  appended on 2026-10-20 08:18 change any amount-probe result (`out/recon_0693.json`).
- **The probe dates are the cause.** Commit 6290fd1 added span probes inside the same per-article loop of `bench.py`,
  which uses the shared random generator. Regenerating the benchmark therefore re-sampled the dates of all 264 amount
  probes; the articles, gold versions and query contexts stay the same (264/264 aligned, 264 dates differ).
  `results_retrieval.json` was written at 03:45:14 (file clock), before that regeneration at 03:54:30.
- **Reconstruction.** Old `bench.py` (4052245 or 6077033) on any store gives every published number exactly: static
  0.239/0.644/0.432, latest 0.117/0.121/0.390, temporal 0.693/0.788/0.000. Today's `bench.py` gives 0.697 on any store,
  and rebuilds `data/bench/tw_taxtime_v0.jsonl` byte for byte.
- **The one probe that flipped:** 所得稅法 Art. 108, query 「不得少於」. On the old date (1999-10-21), Art. 108-1 (in force
  from 1998-01-01) also contains the phrase and ranks first, so it was a miss. On the new date (1996-01-10), Art. 108-1
  was not in force, so it was a hit (`out/recon_0693_flips.json`).
- **Correct number for today's code and data: 0.697 (0.639–0.749)**, i.e. 184/264. The published 0.693 is 183/264 on
  an earlier sample of probe dates. The difference is one probe, well inside the interval. A full re-run of `bench.py`
  on either corrected store also gives 0.697.

## 6. What it means
- **The date errors are real but mostly off the probes' path.** About 6% of article versions (211 of 3,555 under Fix
  A) start on the wrong day, some by a year or more. The probes rarely land in the window between the wrong and the
  right start, so the published retrieval conclusions do not depend on these errors. Every published number moves by
  at most 0.006, and every finding keeps its direction and significance.
- **A rule-graded benchmark cannot see errors in the store it is generated from.** Today's store scores 0% wrong
  versions on its own labels, but 1.5% on labels derived from the corrected dates. Date rules must be checked against
  the official text, not only against benchmarks built from them.
- **The time rules need both layers.** The MOJ history gives most dates. Each act's commencement article catches cases
  the history states only at paragraph level. Neither reader is enough alone.

## 7. Recommendation
1. **Correct 0.693 → 0.697 now** in README, REPORT §4.1 and the application documents. That is the right number for the
   code and data as they are today, whatever is decided about the fixes.
2. **Apply Fix A**, and preferably Fix B, before publishing the store. Both patches apply cleanly in sequence with
   `git apply data/audit/fix_moj_history.patch data/audit/fix_effect_rules.patch`; GNU `patch` trips over the CRLF line
   endings of `build_db.py`. Then run `build_db.py`, `english.py` and `regulations.py`.
3. **Decide how the benchmark is published.** `data/` is gitignored, and `pipeline.py` regenerates the probes,
   which re-samples dates. Either:
   - (a) freeze and publish the probe files and relabel their gold from the corrected store. This gives the "Fix A" or
     "Fix A+B" column, needs no retraining and no LLM, and the audit scripts show how;
   - (b) regenerate everything: version/span/amount/bitemporal counts become 1,224/2,010/264/100 (A) or
     1,223/2,009/264/98 (A+B), temporal R@1 0.697, and the reranker study has to be rebuilt and retrained.

   Option (a) is cheaper and keeps the published probe set.
4. **Update the numbers** listed in §8, and correct one sentence of the README. The 2011-01 所得稅法 amendment took
   effect on 2011-01-21. Only the items on military and teachers' pay (Art. 4 ¶1 items 1–2, Art. 17 ¶1(1)4) started
   on 2012-01-01. The "overtaken" case is the Art. 17 text, not the whole amendment.
5. **Ask a Chinese-reading person** to confirm the six sub-points in §5.2 and the 2009 Art. 5 reading in §5.4.
6. **Tell P0** about the 6 items whose gold depends on Fix B and the 33 or 45 items whose displayed validity dates
   change.
7. **The demo** (`src/app.py`, `web/index.html`) should show pending rows (`valid_from` 9999-12-31) as "not in force
   (date to be set by the Executive Yuan)". This is not done here.

## 8. Published numbers that change if the fixes are applied
| Where | Text today | Fix A | Fix A+B |
|---|---|---|---|
| README results table; REPORT §4.1 | temporal R@1 **0.693 (0.635–0.746)** | 0.697 (0.639–0.749) | 0.693 (0.635–0.746), now 183/264 under corrected labels |
| same | static R@1 0.239 (0.191–0.294); wrong version **0.432 (0.373–0.492)**; abstract "43%" | unchanged | 0.242 (0.195–0.298); 0.428 (0.370–0.488); "43%" unchanged |
| same | latest 0.117 / 0.390; temporal wrong version 0.000 | unchanged | unchanged |
| README reranker table; REPORT §4.2 | BM25 0.474 / 0.198 / **0.746** | 0.471 / 0.200 / 0.744 | 0.471 / 0.200 / 0.742 |
| same | zero-shot 0.537 / 0.155 / 0.751 | 0.538 / 0.154 / 0.751 | 0.532 / 0.160 / 0.748 |
| same | fine-tuned lexical 0.671 / 0.067 / 0.747 | 0.672 / 0.065 / 0.745 | 0.665 / 0.071 / 0.742 |
| same | fine-tuned temporal **0.675** / 0.060 / 0.748 | 0.677 / 0.059 / 0.748 | 0.673 / 0.063 / 0.746 |
| same | fine-tuned mixed 0.673 / 0.072 / 0.751 | 0.674 / 0.070 / 0.750 | 0.669 / 0.075 / 0.747 |
| README findings; abstract | "15.5% → 6–7%" wrong version | 15.4% → 5.9–7.0% | 16.0% → 6.3–7.5% |
| same | "212 vs 50, p < 0.001" | 213 vs 51 | 213 vs 52 |
| same | "54 vs 49, p = 0.69" | 53 vs 47, p = 0.62 | 55 vs 46, p = 0.43 |
| same | "**0.746 vs 0.675 (104 vs 19, p < 0.001)**" | 0.744 vs 0.677 (101 vs 20, p < 0.001) | 0.742 vs 0.673 (103 vs 20, p < 0.001) |
| same | "23 vs 20, p = 0.76" | 24 vs 19, p = 0.54 | 24 vs 19, p = 0.54 |
| README NL paragraph; REPORT §4.3 | correct amount 74%; wrong-version amount 4%; "1 of 11" flagged | unchanged | 72%; 6%; 3 of 13 |
| same | period 100%; @1 58% / @5 80%; abstained 18%; 105 questions | unchanged | unchanged |
| README "Temporal edge cases"; REPORT §2.2 | 54 retroactive article versions; 4 overtaken | unchanged (54 is a different set); 4 | 53; 5 |
| REPORT §2.2 | "§126: 20 rules, 0 unparsed sentences" | unchanged | 21 rules |
| REPORT §3 | 1,225 version / 264 amount / 2,010 span / 104 bitemporal probes | unchanged if the probe file is frozen (regenerated: 1,224/264/2,010/100) | frozen: unchanged (regenerated: 1,223/264/2,009/98) |
| README, REPORT abstract | 23 acts, 406 versions, 3,555 article versions | unchanged | unchanged |

Not changed by either fix: the 23/406/3,555 store counts, 0 overlapping intervals, the "43%" headline, all
significance conclusions, the 105 NL questions and their period, retrieval and abstention rates.
`docs/CHRONOMED.md` (P3) quotes tax-side counts that the fixes change: 46 delayed versions become 56; 0.697 is
already today's number. P3 should re-run its tax column after the fix.

## 9. Limitations
- The verdicts are my reading of the official Chinese texts. Each one is backed by the MOJ history and, where one
  exists, by the statute's own commencement article. Six sub-points still need a Chinese-reading person (§5.2).
- MOJ history and LY statute text are both official, but they are not independent of each other. The web sources are
  local tax-bureau and portal pages.
- The corrected reader was written while reading these 413 entries, so it may be tuned to them. Every date it changes
  was checked by hand (§5.3).
- Paragraph-level exceptions are still applied only through the commencement article (§5.4).
- NL answers were not re-generated (0 LLM calls). Under A+B, 3 grades were re-derived from stored flags. Other answers
  could change slightly because the validity dates in the prompt change.
- The GPU re-scoring used the original `rerank.score` (fp16). It peaked at 1,436 MB allocated, above the 1 GB guideline
  for this agent. The coordinator had reported the GPU free. The A+B run (4 models, all 1,207 probes, plus the touched
  probes) took 2.5 minutes, and the GPU was released afterwards (0 MiB used).

## 10. How to reproduce
From the repository root, with `python -I -B` (abbreviated `py`):
```
py src/audit/compare_readers.py          # 31 differing entries            -> data/audit/out/reader_diff.json
py src/audit/inspect_versions.py         # what the store did per article  -> out/inspect_versions.json
py src/audit/check_patched_reader.py     # corrected reader on all 413     -> out/patched_reader_check.json
py src/audit/build_variants.py original  # determinism check               -> data/audit/lawtw_rebuilt_original.db
py src/audit/build_variants.py fixed     # Fix A                           -> data/audit/lawtw_fixed.db
py src/audit/build_variants.py fixed_ab  # Fix A+B                         -> data/audit/lawtw_fixed_ab.db
py src/audit/compare_dbs.py data/audit/lawtw_current_copy.db data/audit/lawtw_fixed.db data/audit/out/cmp_current_vs_fixed.json
py src/audit/review_changes.py           # changes grouped by amendment    -> out/change_groups.json
py src/audit/store_stats.py              # store counts                    -> out/store_stats.json
py src/audit/eval_amount.py              # 264 amount probes, paired       -> out/eval_amount.json
py src/audit/recon_0693.py               # 0.693 vs 0.697                  -> out/recon_0693.json
set HF_HUB_OFFLINE=1
py src/audit/rerank_filter.py --score    # 1,207 probes, GPU fp16          -> out/rerank_filter.json
py src/audit/nl_and_items.py             # NL retrieval + P0 items         -> out/nl_and_items.json
py src/audit/verdicts.py                 # verdict table                   -> out/verdicts.json
py src/audit/summary_numbers.py          # all published numbers           -> out/summary_numbers.json
```
For Fix A+B, set `AUDIT_FIXED_DB=data/audit/lawtw_fixed_ab.db` and `AUDIT_TAG=_ab` before the compare and
evaluation steps; the outputs get the suffix `_ab`.
