"""Step 1: run the ORIGINAL MOJ history reader (src/moj_history.py) and P3's extended reader (src/med/moj_med.py)
on the 23 cached tax history pages and list every entry whose amendment-level effective date differs.

  python -I -B src/audit/compare_readers.py   -> data/audit/out/reader_diff.json (+ console table)

Checks that the two readers see the same entries (same numbers, same promulgation dates) and that P3's positional
pairing (zip after sorting) equals pairing by entry number, so the count of differences is not an alignment artefact.
For each entry we also report the LY version that build_db.match_versions pairs it with, and what the CURRENT store
(data/audit/lawtw_current_copy.db, version table) records for that version.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402  (sets sys.path, dont_write_bytecode)
from common import CUR_DB, MED_SRC, OUT, ly_meta, ro, sha256, tax_pages, write_json  # noqa: E402

import build_db  # noqa: E402  original, imported unchanged (match_versions)
import moj_history  # noqa: E402  original reader

sys.path.insert(0, str(MED_SRC))
import moj_med  # noqa: E402  P3's reader (its import of medcfg re-points original module paths into data/med/;
#                 we only call pure functions: moj_history.parse, moj_med.parse, build_db.match_versions)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    pages = tax_pages()
    con = ro(CUR_DB)
    rows, n, n_zip_diff, problems = [], 0, 0, []
    for lid, (pcode, page) in pages.items():
        a, b = moj_history.parse(page), moj_med.parse(page)
        if len(a) != len(b):
            problems.append(f"{lid}: entry count {len(a)} vs {len(b)}")
        # P3's method: positional zip
        n_zip_diff += sum(x["effective"] != y["effective"] for x, y in zip(a, b))
        if [x["no"] for x in a] != [y["no"] for y in b]:
            problems.append(f"{lid}: entry order differs between readers")
        bn = {y["no"]: y for y in b}
        meta = ly_meta(lid)
        pairs = build_db.match_versions(meta["versions"], a)
        ly_of = {m["no"]: v for v, m in pairs if m}
        for x in a:
            n += 1
            y = bn.get(x["no"])
            if y is None:
                problems.append(f"{lid} no {x['no']}: missing in extended reader")
                continue
            if x["promulgated"] != y["promulgated"]:
                problems.append(f"{lid} no {x['no']}: promulgation {x['promulgated']} vs {y['promulgated']}")
            if x["effective"] == y["effective"]:
                continue
            v = ly_of.get(x["no"])
            stored = con.execute("SELECT ly_version, effective, effective_basis FROM version WHERE law_id=? AND moj_no=?",
                                 (lid, x["no"])).fetchall()
            name = con.execute("SELECT name FROM law WHERE law_id=?", (lid,)).fetchone()[0]
            rows.append({
                "law_id": lid, "law": name, "pcode": pcode, "no": x["no"], "promulgated": x["promulgated"],
                "ly_version": v["版本編號"] if v else None, "ly_date": v["日期"] if v else None,
                "orig_effective": x["effective"], "orig_basis": x["effective_basis"],
                "new_effective": y["effective"], "new_basis": y["effective_basis"],
                "new_rules": y["rules"], "new_partial": y["partial"], "new_pending": y["pending_refs"],
                "new_unparsed": y["unparsed"], "commencement_text_new": y["commencement_text"],
                "stored_in_db": [dict(r) for r in stored],
                "note": x["note"],
            })
    out = {"p3_reader": str(MED_SRC / "moj_med.py"), "p3_reader_sha256": sha256(MED_SRC / "moj_med.py"),
           "orig_reader_sha256": sha256(common.SRC / "moj_history.py"),
           "entries": n, "differences_by_entry_no": len(rows), "differences_positional_zip": n_zip_diff,
           "alignment_problems": problems, "differences": rows}
    write_json(OUT / "reader_diff.json", out)
    print(f"entries {n}; differ (by entry no) {len(rows)}; differ (positional zip, P3 method) {n_zip_diff}; "
          f"alignment problems {problems or 'none'}")
    for r in rows:
        print(f"{r['law_id']} {r['law']} #{r['no']} prom {r['promulgated']} LY {r['ly_version']} | orig {r['orig_effective']} "
              f"({r['orig_basis']}) | new {r['new_effective']} ({r['new_basis']}) | in DB: "
              f"{[(s['effective'], s['effective_basis']) for s in r['stored_in_db']]}")


if __name__ == "__main__":
    main()
