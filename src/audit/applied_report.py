"""Tables for data/audit/APPLIED.md: old (pre-fix files) -> new (regenerated files in the repo) for every published
number, store counts (backup store vs data/lawtw.db), and P0 verifier items affected by the date fix.

  python -I -B src/audit/applied_report.py   -> data/audit/out/applied_tables.md, data/audit/out/applied_p0_items.json
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BENCH, OUT, ROOT, write_json  # noqa: E402

PRE = BENCH / "_prefix_2026-10-26"
OLD_DB = ROOT / "data" / "backup_before_datefix" / "lawtw.db"
NEW_DB = ROOT / "data" / "lawtw.db"
IN_FORCE = "valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"


def ro(p):
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def j(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def ci(v, c):
    return f"{v:.3f} ({c[0]:.3f}–{c[1]:.3f})"


def store(con):
    W = "law_id NOT LIKE 'G%'"
    one = lambda q: con.execute(q).fetchone()[0]  # noqa: E731
    cols = [x[1] for x in con.execute("PRAGMA table_info(article_version)")]
    return {"acts": one(f"SELECT count(*) FROM law WHERE {W}"), "versions": one(f"SELECT count(*) FROM version WHERE {W}"),
            "article versions": one(f"SELECT count(*) FROM article_version WHERE {W} AND deleted=0"),
            "retroactive article versions": one(f"SELECT count(*) FROM article_version WHERE {W} AND deleted=0 AND retro=1"),
            "overtaken pending article versions": one(f"SELECT count(*) FROM article_version WHERE {W} AND overtaken=1"),
            "articles not in force yet (pending)": one(f"SELECT count(*) FROM article_version WHERE {W} AND pending=1")
            if "pending" in cols else 0,
            "overlapping non-empty intervals": one(
                f"SELECT count(*) FROM article_version a JOIN article_version b ON a.law_id=b.law_id AND a.article_no="
                f"b.article_no AND a.id<b.id WHERE a.{W} AND a.valid_to IS NOT a.valid_from AND b.valid_to IS NOT "
                "b.valid_from AND a.valid_from < coalesce(b.valid_to,'9999-99') AND b.valid_from < coalesce(a.valid_to,'9999-99')"),
            "Income Tax Act §126 commencement rules": one("SELECT count(*) FROM commencement_rule WHERE law_id='01513'")}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    old, new = ro(OLD_DB), ro(NEW_DB)
    rows = []
    so, sn = store(old), store(new)
    rows += [("store", k, so[k], sn[k]) for k in so]
    changed = [r[0] for r in new.execute("SELECT n.id FROM article_version n WHERE n.law_id NOT LIKE 'G%'")
               if tuple(old.execute("SELECT valid_from FROM article_version WHERE id=?", (r[0],)).fetchone())
               != tuple(new.execute("SELECT valid_from FROM article_version WHERE id=?", (r[0],)).fetchone())]
    rows.append(("store", "article versions with a new start date", 0, len(changed)))
    ro_, rn = j(PRE / "results_retrieval.json"), j(BENCH / "results_retrieval.json")
    for m, lab in (("static", "all versions, date ignored"), ("latest", "today's text only"), ("temporal", "in force on the date")):
        rows.append(("retrieval, 264 amount probes", f"{lab}: R@1", ci(ro_[m]["R@1"], ro_[m]["R@1_ci"]), ci(rn[m]["R@1"], rn[m]["R@1_ci"])))
        rows.append(("retrieval, 264 amount probes", f"{lab}: R@5", ro_[m]["R@5"], rn[m]["R@5"]))
        rows.append(("retrieval, 264 amount probes", f"{lab}: right article, wrong version @1",
                     ci(ro_[m]["misgrounding@1"], ro_[m]["misgrounding@1_ci"]), ci(rn[m]["misgrounding@1"], rn[m]["misgrounding@1_ci"])))
    qo, qn = j(PRE / "results_rerank.json"), j(BENCH / "results_rerank.json")
    for k in qo:
        if k.startswith("_"):
            continue
        rows.append(("reranker, 1,207 probes", f"{k}: R@1", ci(qo[k]["R@1"], qo[k]["R@1_ci"]), ci(qn[k]["R@1"], qn[k]["R@1_ci"])))
        rows.append(("reranker, 1,207 probes", f"{k}: wrong version @1", f"{qo[k]['misgrounding@1']:.3f}", f"{qn[k]['misgrounding@1']:.3f}"))
    for k, v in qo["_mcnemar"].items():
        w = qn["_mcnemar"][k]
        rows.append(("reranker McNemar", k, f"{v['only_A']} vs {v['only_B']}, p={v['p']}", f"{w['only_A']} vs {w['only_B']}, p={w['p']}"))
    no, nn = j(PRE / "results_nl.json")["summary"], j(BENCH / "results_nl.json")["summary"]
    for k in ("year_ok", "r1", "r5", "amount_ok", "distractor", "all_verified", "insufficient"):
        rows.append(("NL, 105 questions", k, ci(no[k]["rate"], no[k]["ci"]), ci(nn[k]["rate"], nn[k]["ci"])))
    rows.append(("NL, 105 questions", "wrong answers flagged by code",
                 f"{no['wrong_answers_flagged_by_code']['flagged']} of {no['wrong_answers_flagged_by_code']['n']}",
                 f"{nn['wrong_answers_flagged_by_code']['flagged']} of {nn['wrong_answers_flagged_by_code']['n']}"))
    so_, sn_ = j(PRE / "summary.json"), j(BENCH / "summary.json")
    rows.append(("benchmark", "probes by type", json.dumps(so_["by_type"]), json.dumps(sn_["by_type"])))
    rl = j(OUT / "relabel_log.json")
    rows.append(("benchmark", "probes with a new gold label (TW-TaxTime / reranker / NL rows)", "—",
                 f"{rl['counts']['tw_taxtime_v0']} / {rl['counts']['rerank_test']} / {rl['counts']['tw_taxtime_nl']}"))
    # A+B column of the audit, to check equality
    ab = {(r["group"], r["number"]): r["fix_AB"] for r in j(OUT / "summary_numbers.json")}
    md = ["| Group | Number | Before (pre-fix files / backup store) | After (repo now) | = audit A+B column? |",
          "|---|---|---|---|---|"]
    def abv(g, k):
        g2 = {"retrieval, 264 amount probes": "retrieval (264 amount probes)", "reranker, 1,207 probes": "reranker (1,207 probes)",
              "reranker McNemar": "reranker McNemar", "NL, 105 questions": "NL (105 questions)", "store": "store"}.get(g)
        k2 = k.replace("in force on the date", "versions in force on the date")
        k2 = {"retroactive article versions": "retroactive article versions (README 54)",
              "overtaken pending article versions": "overtaken pending article versions (README 4)",
              "overlapping non-empty intervals": "overlapping non-empty intervals (REPORT 0)",
              "articles not in force yet (pending)": "article versions not in force yet (pending)"}.get(k2, k2)
        return ab.get((g2, k2))
    checks = []
    for g, k, a, b in rows:
        e = abv(g, k)
        eq = "" if e is None else ("yes" if str(e).split(" (")[0] == str(b).split(" (")[0].replace("p=0.0", "p=0.0") else f"NO ({e})")
        if e is not None:
            checks.append(eq == "yes")
        md.append(f"| {g} | {k} | {a} | {b} | {eq} |")
    (OUT / "applied_tables.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    # P0 items
    vi = [json.loads(l) for l in (ROOT / "data" / "verifier" / "items.jsonl").open(encoding="utf-8")]
    lab, val = [], []
    for it in vi:
        d = (it.get("period") or {}).get("as_of")
        def g(con):
            r = con.execute(f"SELECT id, deleted FROM article_version WHERE law_id=? AND article_no=? AND {IN_FORCE} "
                            "ORDER BY valid_from DESC, id DESC", (it["law_id"], it["article"], d, d)).fetchall()
            return (None if r[0]["deleted"] else r[0]["id"]) if r else None
        if d and it.get("law_id") and it.get("article") and g(old) != g(new):
            lab.append({"item_id": it["item_id"], "probe_id": it.get("probe_id"), "as_of": d, "old_version": g(old),
                        "new_version": g(new)})
        srcs = [s for s in (it.get("reference") or {}).get("sources", []) if s.get("kind") == "article_version"]
        cited = it.get("cited") or {}
        if cited.get("kind") == "article_version":
            srcs.append(cited)
        diffs = []
        for s in srcs:
            if not str(s.get("source_id", "")).isdigit():
                continue
            a_ = old.execute("SELECT valid_from, valid_to FROM article_version WHERE id=?", (int(s["source_id"]),)).fetchone()
            b_ = new.execute("SELECT valid_from, valid_to FROM article_version WHERE id=?", (int(s["source_id"]),)).fetchone()
            if a_ and b_ and tuple(a_) != tuple(b_):
                diffs.append({"source_id": int(s["source_id"]), "old": list(a_), "new": list(b_)})
        if diffs:
            uniq = {d_["source_id"]: d_ for d_ in diffs}
            val.append({"item_id": it["item_id"], "probe_id": it.get("probe_id"), "versions": list(uniq.values())})
    write_json(OUT / "applied_p0_items.json", {"label_changed": lab, "validity_interval_changed": val})
    print("\n".join(md))
    print(f"rows checked against A+B: {len(checks)}, all equal: {all(checks)}")
    print("P0 label changed:", [x["item_id"] for x in lab])
    print("P0 validity changed:", len(val), sorted({x['probe_id'] for x in val}))


if __name__ == "__main__":
    main()
