"""Compare two tax-store files row by row.

  python -I -B src/audit/compare_dbs.py A.db B.db OUT.json

Tax acts (law_id not starting with 'G'): version rows and article_version rows by id (all columns);
regulation rows (law_id 'G…', appended by regulations.py) by content, ignoring ids; article_en by key.
Reports which article versions changed their interval / basis, and checks that ids, texts and articles are identical.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ro, write_json  # noqa: E402

AV_COLS = ["law_id", "article_no", "seq", "chapter", "text", "first_ly_version", "valid_from", "valid_to", "from_basis",
           "published", "retro", "deleted", "overtaken"]
DATE_COLS = ["valid_from", "valid_to", "from_basis", "retro", "overtaken", "pending"]


def cols(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def main(a_path: str, b_path: str, out: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a, b = ro(Path(a_path)), ro(Path(b_path))
    res = {"a": a_path, "b": b_path}
    # versions
    va = {(r["law_id"], r["ly_version"]): dict(r) for r in a.execute("SELECT * FROM version WHERE law_id NOT LIKE 'G%'")}
    vb = {(r["law_id"], r["ly_version"]): dict(r) for r in b.execute("SELECT * FROM version WHERE law_id NOT LIKE 'G%'")}
    res["versions"] = [len(va), len(vb)]
    vdiff = []
    for k in sorted(set(va) | set(vb)):
        x, y = va.get(k), vb.get(k)
        if x != y:
            vdiff.append({"key": k, "fields": {c: [x and x.get(c), y and y.get(c)] for c in (x or y)
                                                if (x or {}).get(c) != (y or {}).get(c)}})
    res["version_rows_differing"] = len(vdiff)
    res["version_fields_differing"] = sorted({c for d in vdiff for c in d["fields"]})
    res["version_date_changes"] = [d for d in vdiff if set(d["fields"]) - {"moj_note"}]
    # article versions
    ca, cb = cols(a, "article_version"), cols(b, "article_version")
    ra = {r["id"]: dict(r) for r in a.execute("SELECT * FROM article_version WHERE law_id NOT LIKE 'G%'")}
    rb = {r["id"]: dict(r) for r in b.execute("SELECT * FROM article_version WHERE law_id NOT LIKE 'G%'")}
    res["article_version_rows"] = [len(ra), len(rb)]
    res["article_version_non_deleted"] = [sum(not r["deleted"] for r in ra.values()), sum(not r["deleted"] for r in rb.values())]
    res["ids_identical"] = set(ra) == set(rb)
    ident = ["law_id", "article_no", "text", "first_ly_version", "seq", "chapter", "published", "deleted"]
    res["identity_mismatch_ids"] = [i for i in set(ra) & set(rb) if any(ra[i][c] != rb[i][c] for c in ident)][:50]
    changed = []
    for i in sorted(set(ra) & set(rb)):
        x, y = ra[i], rb[i]
        f = {c: [x.get(c, 0), y.get(c, 0)] for c in DATE_COLS if x.get(c, 0) != y.get(c, 0)}
        if f:
            changed.append({"id": i, "law_id": x["law_id"], "article_no": x["article_no"],
                            "first_ly_version": x["first_ly_version"], "deleted": x["deleted"], **f})
    res["article_versions_changed"] = len(changed)
    res["article_versions_changed_non_deleted"] = sum(not c["deleted"] for c in changed)
    res["article_versions_valid_from_changed_non_deleted"] = sum(("valid_from" in c) and not c["deleted"] for c in changed)
    res["changed_columns_count"] = {c: sum(c in x for x in changed) for c in DATE_COLS}
    res["changed"] = changed
    # regulations and English gloss
    rega = sorted(tuple(r) for r in a.execute("SELECT law_id, article_no, text, valid_from, valid_to, from_basis FROM "
                                              "article_version WHERE law_id LIKE 'G%'"))
    regb = sorted(tuple(r) for r in b.execute("SELECT law_id, article_no, text, valid_from, valid_to, from_basis FROM "
                                              "article_version WHERE law_id LIKE 'G%'"))
    res["regulation_rows_identical_ignoring_ids"] = rega == regb
    ena = sorted(tuple(r) for r in a.execute("SELECT * FROM article_en"))
    enb = sorted(tuple(r) for r in b.execute("SELECT * FROM article_en"))
    res["article_en_identical"] = ena == enb
    cra = sorted(tuple(r) for r in a.execute("SELECT * FROM commencement_rule"))
    crb = sorted(tuple(r) for r in b.execute("SELECT * FROM commencement_rule"))
    res["commencement_rule_identical"] = cra == crb
    write_json(Path(out), res)
    for k, v in res.items():
        if k not in ("changed", "version_date_changes", "identity_mismatch_ids"):
            print(f"{k}: {v}")
    print("identity mismatches:", res["identity_mismatch_ids"][:10])


if __name__ == "__main__":
    main(*sys.argv[1:4])
