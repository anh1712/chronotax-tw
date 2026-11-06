"""Group the interval changes (current store -> corrected store) by amendment, and tie each group to one of the 31
differing MOJ entries (D01..D31) or mark it EXTRA (an entry outside P3's 31).

  python -I -B src/audit/review_changes.py   -> data/audit/out/change_groups.json (+ console)
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CUR_DB, FIXED_DB, OUT, TAG, ro, write_json  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cmp_ = json.loads((OUT / f"cmp_current_vs_fixed{TAG}.json").read_text(encoding="utf-8"))
    diff31 = json.loads((OUT / "reader_diff.json").read_text(encoding="utf-8"))["differences"]
    dlabel = {(r["law_id"], r["ly_version"]): f"D{i:02d}" for i, r in enumerate(diff31, 1)}
    cur, fix = ro(CUR_DB), ro(FIXED_DB)
    names = {r["law_id"]: r["name"] for r in cur.execute("SELECT law_id, name FROM law")}
    groups = collections.OrderedDict()
    for c in cmp_["changed"]:
        if "valid_from" not in c and "valid_to" not in c and "pending" not in c:
            continue
        a = cur.execute("SELECT * FROM article_version WHERE id=?", (c["id"],)).fetchone()
        b = fix.execute("SELECT * FROM article_version WHERE id=?", (c["id"],)).fetchone()
        key = (a["law_id"], a["first_ly_version"])
        g = groups.setdefault(key, {"law_id": key[0], "law": names[key[0]], "ly_version": key[1],
                                    "d": dlabel.get(key, "EXTRA" if "valid_from" in c else "end-only"),
                                    "start_changed": [], "end_only": []})
        row = {"id": a["id"], "article": a["article_no"], "old": [a["valid_from"], a["valid_to"], a["from_basis"]],
               "new": [b["valid_from"], b["valid_to"], b["from_basis"]], "pending": b["pending"]}
        (g["start_changed"] if a["valid_from"] != b["valid_from"] else g["end_only"]).append(row)
    out = list(groups.values())
    for g in out:  # label after all rows are in: D01..D31, EXTRA (start moved, outside the 31) or end-only
        g["d"] = dlabel.get((g["law_id"], g["ly_version"])) or ("EXTRA" if g["start_changed"] else "end-only")
    write_json(OUT / f"change_groups{TAG}.json", out)
    n_start = sum(len(g["start_changed"]) for g in out)
    print(f"groups {len(out)}; article versions with a new start date {n_start}; with only a new end date "
          f"{sum(len(g['end_only']) for g in out)}")
    for g in out:
        if not g["start_changed"]:
            continue
        pairs = collections.Counter((r["old"][0], r["new"][0], r["new"][2]) for r in g["start_changed"])
        print(f"{g['d']:6s} {g['law_id']} {g['law']} {g['ly_version']}: {len(g['start_changed'])} start "
              f"{dict(pairs)} | end-only {len(g['end_only'])}")
        for r in g["start_changed"]:
            if r["pending"] or g["d"] == "EXTRA" or len(g["start_changed"]) <= 3:
                print(f"        {r['article']} {r['old'][0]}→{r['new'][0]} ({r['old'][2]} → {r['new'][2]})"
                      f"{' PENDING' if r['pending'] else ''}")


if __name__ == "__main__":
    main()
