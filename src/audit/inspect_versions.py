"""For each of the 31 differing MOJ entries: the article versions the CURRENT store created from that LY version,
with their valid_from / from_basis, and the per-article commencement rules (table commencement_rule) that match the
amendment. Shows where the act's own commencement article (e.g. 所得稅法 §126) already overrides the version date.

  python -I -B src/audit/inspect_versions.py   -> data/audit/out/inspect_versions.json (+ console)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CUR_DB, OUT, ro, write_json  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    d = json.loads((OUT / "reader_diff.json").read_text(encoding="utf-8"))
    con = ro(CUR_DB)
    res = []
    for i, r in enumerate(d["differences"], 1):
        v = con.execute("SELECT * FROM version WHERE law_id=? AND moj_no=?", (r["law_id"], r["no"])).fetchone()
        dates = {v["ly_date"], v["promulgated"]}
        rules = [dict(x) for x in con.execute("SELECT * FROM commencement_rule WHERE law_id=?", (r["law_id"],))
                 if x["amend_date"] in dates]
        avs = [dict(x) for x in con.execute(
            "SELECT id, article_no, valid_from, valid_to, from_basis, deleted, overtaken, retro FROM article_version "
            "WHERE law_id=? AND first_ly_version=? ORDER BY seq, id", (r["law_id"], v["ly_version"]))]
        res.append({"d": f"D{i:02d}", "law_id": r["law_id"], "no": r["no"], "ly_version": v["ly_version"],
                    "version_effective": v["effective"], "version_basis": v["effective_basis"],
                    "rules_for_this_amendment": rules, "article_versions": avs})
        print(f"=== D{i:02d} {r['law_id']} {r['law']} #{r['no']} {v['ly_version']} version eff {v['effective']} "
              f"({v['effective_basis']}); orig {r['orig_effective']} new {r['new_effective']}")
        for x in rules:
            print(f"   rule: amend {x['amend_date']} arts {x['articles']} -> {x['effective']} ({x['basis']})")
        for a in avs:
            print(f"   av#{a['id']} {a['article_no']} {a['valid_from']}→{a['valid_to']} {a['from_basis']}"
                  f"{' DELETED' if a['deleted'] else ''}{' OVERTAKEN' if a['overtaken'] else ''}{' retro' if a['retro'] else ''}")
    write_json(OUT / "inspect_versions.json", res)


if __name__ == "__main__":
    main()
