"""Verdicts for the 31 MOJ history entries where the original and P3's reader disagree (the audit's reading of the
official text), merged with what each reader said and with the measured article-level change in the corrected store.

  python -I -B src/audit/verdicts.py   -> data/audit/out/verdicts.json, data/audit/out/verdicts_table.md

Verdict = which reader's AMENDMENT-LEVEL reading matches the official text: original | new | split (each reader is right
for some articles, wrong for others). Evidence: H = the MOJ history entry itself (cached page, data/raw/moj);
S = the act's own commencement article in the latest LY text (data/raw/ly); W = official web source in
data/audit/out/sources.json. "human" lists the points a Chinese-reading human should confirm.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, write_json  # noqa: E402

A, B, C, D, E, F, G, H = ("line-wrap space inside the clause", "last date taken for the whole amendment, but it is an "
                          "exception for some articles/paragraphs", "tax-year form 自…年度施行 not read",
                          "relative date 自公布後一年施行 not read", "form 定於…施行 not read",
                          "new reader leaves the amendment undated when Executive Yuan orders name its articles",
                          "delegated articles with no order (not in force)", "application period 施行期間 not read")
V = {  # D: (verdict, cause letters, correct reading, evidence, needs human check)
    1: ("new", "B", "Arts 5-1, 17 from 1993-01-01; Art.126 by §13 (1993-02-07)", "H", ""),
    2: ("new", "A", "whole amendment 2001-07-01", "H; S (date delegated to Executive Yuan)", ""),
    3: ("new", "B", "main §13 2008-01-04; only Art.14 ¶1 cat.9 from 2008-01-01", "H; S §126", ""),
    4: ("split", "C", "Art.5 ¶5 from tax year 2010 (new reader); Art.126 by §13 2010-06-17 (original)", "H; S §126", ""),
    5: ("new", "B", "main §13 2011-01-21; Arts 4 ¶1 items 1-2 and 17 ¶1(1)4 from 2012-01-01 (these items are the only "
        "changes in Arts 4 and 17, checked by text diff)", "H; S §126", ""),
    6: ("new", "A+C", "Arts 66-4, 66-6, 73-2 from 2015-01-01; rest from tax year 2015", "H; S §126", ""),
    7: ("new", "A", "2016-01-01", "H; S §126", ""),
    8: ("new", "G+C", "Art.17-4 2016-08-01; Art.43-3 from tax year 2023; Art.43-4 not in force", "H; W S3 (MOJ notice)",
        "date of the amended Art.126 itself"),
    9: ("new", "B", "main 2018-01-01; 7 articles tax year 2018; Art.73-2 2019-01-01", "H; S §126", ""),
    10: ("new", "A", "2019-01-01", "H; S §126", ""),
    11: ("new", "B", "2006-01-01; Art.15 2007-01-01; Art.12 ¶1 item 1 2010-01-01 (paragraph)", "H; S §18", ""),
    12: ("new", "C", "tax year 2013", "H; S §18", ""),
    13: ("original", "F", "Arts 16, 20 from 2002-01-01 (every amended article)", "H", ""),
    14: ("new", "E", "Art.8 from 1997-12-01 (Executive Yuan order)", "H; S §60", ""),
    15: ("new", "E", "Art.53-1 from 1998-07-10 (Executive Yuan order)", "H; S §60", ""),
    16: ("original", "F", "Art.11 from 2003-07-01 (the only amended article)", "H", ""),
    17: ("new", "B", "18 articles 2011-04-01; Arts 16, 20 2011-09-01 (two orders)", "H", ""),
    18: ("new", "A", "2011-07-01 (Executive Yuan order)", "H; S §51", ""),
    19: ("new", "B", "main §13 2021-12-19; Art.20 2022-01-01", "H; S §51", ""),
    20: ("new", "D", "one year after promulgation: 2017-12-28", "H; S §23; W S1, S2", ""),
    21: ("new", "D", "2026-05-28", "H; W S2", ""),
    22: ("new", "B", "main §13 2024-01-05; Arts 4–7 (incl. 6-1), 12, 15 from 2024-07-01", "H; S §25; W S5 (6-1)",
         "whether 第4～7條 covers Art.6-1 (official portal says the 6-1 rule applies from 2024-07)"),
    23: ("new", "A", "2001-07-01", "H; S §33 (delegated)", ""),
    24: ("new", "B", "main §13 2014-06-20; Art.7 2015-01-01", "H; S §38", ""),
    25: ("new", "A", "Arts 1–12 §13 1990-01-26; rest 1990-06-01 (Executive Yuan letter)", "H", ""),
    26: ("original", "F", "Arts 3, 13–15, 17, 18, 32 from 2002-01-01 (new reader also misreads 第13條至15條)", "H; S §37",
         "dates of Art.37 itself and of the deletion of Art.5 (not named in the order)"),
    27: ("original", "F", "Art.12 from 2002-01-01", "H; S §37", "date of Art.37 itself"),
    28: ("original", "F", "Arts 8, 11 from 2026-01-01", "H; S §37", "date of Art.37 itself"),
    29: ("original", "F", "Art.8 from 2009-06-01 (the only amended article)", "H", ""),
    30: ("new", "A", "2011-06-01 (Executive Yuan order)", "H; S §26", ""),
    31: ("split", "G+H", "main §13 2025-05-09 (new reader right); Arts 22, 67-3 not in force (new reader right); Art.23-2 "
         "applies from 2025-01-01 (both readers wrong)", "H; S §72; W S4", ""),
}
CAUSE = dict(zip("ABCDEFGH", (A, B, C, D, E, F, G, H)))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    diff = json.loads((OUT / "reader_diff.json").read_text(encoding="utf-8"))["differences"]
    groups = {(g["law_id"], g["ly_version"]): g for g in json.loads((OUT / "change_groups.json").read_text(encoding="utf-8"))}
    rows = []
    for i, r in enumerate(diff, 1):
        v, cause, reading, ev, human = V[i]
        g = groups.get((r["law_id"], r["ly_version"]), {"start_changed": []})
        rows.append({"d": f"D{i:02d}", "law_id": r["law_id"], "law": r["law"], "moj_no": r["no"], "promulgated": r["promulgated"],
                     "ly_version": r["ly_version"], "original": [r["orig_effective"], r["orig_basis"]],
                     "new": [r["new_effective"], r["new_basis"]], "verdict": v, "causes": [CAUSE[c] for c in cause.split("+")],
                     "cause_codes": cause, "official_reading": reading, "evidence": ev, "human_check": human,
                     "article_versions_new_start_in_fixed_store": len(g["start_changed"]),
                     "raw_history_text": r["note"].split(":::")[0].strip()})
    counts = {k: sum(x["verdict"] == k for x in rows) for k in ("original", "new", "split")}
    causes = {}
    for x in rows:
        c0 = x["cause_codes"].split("+")[0]
        causes[c0] = causes.get(c0, 0) + 1
    write_json(OUT / "verdicts.json", {"counts": counts, "primary_cause_counts": {CAUSE[k]: v for k, v in sorted(causes.items())},
                                       "cause_codes": CAUSE, "entries": rows})
    lines = ["| D | Act, MOJ entry (promulgated) | LY version | Original reader | New (P3) reader | Verdict | Cause | "
             "Official reading | Evidence | Article versions re-dated |", "|---|---|---|---|---|---|---|---|---|---|"]
    for x in rows:
        o = f"{x['original'][0] or '—'} ({x['original'][1]})"
        n = f"{x['new'][0] or '—'} ({x['new'][1]})"
        lines.append(f"| {x['d']} | {x['law']} #{x['moj_no']} ({x['promulgated']}) | {x['ly_version'].split(':')[1]} | {o} | {n} | "
                     f"**{x['verdict']}** | {x['cause_codes']} | {x['official_reading']}"
                     f"{' — *check: ' + x['human_check'] + '*' if x['human_check'] else ''} | {x['evidence']} | "
                     f"{x['article_versions_new_start_in_fixed_store']} |")
    (OUT / "verdicts_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(counts, {CAUSE[k][:40]: v for k, v in sorted(causes.items())},
          "re-dated:", sum(x["article_versions_new_start_in_fixed_store"] for x in rows))


if __name__ == "__main__":
    main()
