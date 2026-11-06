"""TW-TaxTime v0 amount probes (264): static / latest / temporal, current store vs corrected store.

  python -I -B src/audit/eval_amount.py [BENCH.jsonl] [OUT.json]
     default bench: data/bench/tw_taxtime_v0.jsonl (read-only) -> data/audit/out/eval_amount.json

Uses the ORIGINAL src/eval_retrieval.run() unchanged, called one probe at a time (so outcomes can be paired; the
aggregate equals run() on all probes). Gold labels:
  gold_orig    the probe's gold_version_id (labelled with the CURRENT store's intervals)
  gold_fixed   the article version in force on the probe date in the CORRECTED store (same probe, same date)
Runs: current/gold_orig (reproduces today's number), fixed/gold_fixed (corrected), current/gold_fixed (today's
system graded against corrected labels). Exact McNemar (src/rerank.mcnemar, unchanged) between paired runs.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BENCH, CUR_DB, FIXED_DB, OUT, TAG, ro, write_json  # noqa: E402

import eval_retrieval  # noqa: E402  original
from eval_retrieval import MODES, wilson  # noqa: E402
from rerank import mcnemar  # noqa: E402  original (exact two-sided McNemar)

IN_FORCE = "valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"


def gold_in(con, it) -> int | None:
    r = con.execute(f"SELECT id, deleted FROM article_version WHERE law_id=? AND article_no=? AND {IN_FORCE} "
                    "ORDER BY valid_from DESC, id DESC", (it["law_id"], it["article"], it["as_of"], it["as_of"])).fetchall()
    return (None if r[0][1] else r[0][0]) if r else None


def per_probe(con, items, mode):
    out = []
    for it in items:
        r = eval_retrieval.run(con, [it], mode)
        out.append({"r1": r["R@1"] == 1.0, "r5": r["R@5"] == 1.0, "mis": r["misgrounding@1"] == 1.0})
    return out


def summ(rows):
    n = len(rows)
    k1, k5, km = (sum(r[x] for r in rows) for x in ("r1", "r5", "mis"))
    return {"n": n, "R@1": round(k1 / n, 3), "R@1_ci": wilson(k1, n), "R@5": round(k5 / n, 3),
            "misgrounding@1": round(km / n, 3), "misgrounding@1_ci": wilson(km, n), "hits@1": k1, "mis@1": km}


def main(bench: str | None = None, out: str | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    bench = Path(bench) if bench else BENCH / "tw_taxtime_v0.jsonl"
    items = [json.loads(l) for l in bench.open(encoding="utf-8")]
    items = [i for i in items if i["type"] == "amount"]
    cur, fix = ro(CUR_DB), ro(FIXED_DB)
    changed_gold = []
    items_fixed = []
    for it in items:
        g_cur, g_fix = gold_in(cur, it), gold_in(fix, it)
        assert g_cur == it["gold_version_id"], (it["id"], g_cur, it["gold_version_id"])  # labels match today's store
        if g_fix != it["gold_version_id"]:
            changed_gold.append({"id": it["id"], "law_id": it["law_id"], "article": it["article"], "as_of": it["as_of"],
                                 "gold_orig": it["gold_version_id"], "gold_fixed": g_fix})
        items_fixed.append({**it, "gold_version_id": g_fix if g_fix is not None else -1})
    runs = {"current/gold_orig": (cur, items), "fixed/gold_fixed": (fix, items_fixed), "current/gold_fixed": (cur, items_fixed)}
    res = {"bench": str(bench), "n": len(items), "gold_changed": changed_gold, "runs": {}, "mcnemar_R@1": {},
           "mcnemar_mis@1": {}, "flipped": {}}
    hits = {}
    for name, (con, its) in runs.items():
        res["runs"][name] = {}
        for m in MODES:
            pp = per_probe(con, its, m)
            hits[(name, m)] = pp
            res["runs"][name][m] = summ(pp)
            agg = eval_retrieval.run(con, its, m)  # the original aggregate, for the record
            assert agg["R@1"] == res["runs"][name][m]["R@1"], (name, m)
    for m in MODES:
        for a, b in (("fixed/gold_fixed", "current/gold_orig"), ("current/gold_fixed", "current/gold_orig")):
            ha, hb = hits[(a, m)], hits[(b, m)]
            res["mcnemar_R@1"][f"{m}: {a} vs {b}"] = mcnemar([x["r1"] for x in ha], [x["r1"] for x in hb])
            res["mcnemar_mis@1"][f"{m}: {a} vs {b}"] = mcnemar([x["mis"] for x in ha], [x["mis"] for x in hb])
            res["flipped"][f"{m}: {a} vs {b}"] = [items[i]["id"] for i in range(len(items))
                                                  if ha[i]["r1"] != hb[i]["r1"] or ha[i]["mis"] != hb[i]["mis"]]
    write_json(Path(out) if out else OUT / f"eval_amount{TAG}.json", res)
    print(f"{bench.name}: {len(items)} amount probes; gold changes under corrected dates: {len(changed_gold)}")
    for g in changed_gold:
        print("   ", g)
    for name in runs:
        for m in MODES:
            r = res["runs"][name][m]
            print(f"{name:20s} {m:9s} R@1 {r['R@1']} {r['R@1_ci']} R@5 {r['R@5']} wrong-version@1 {r['misgrounding@1']} "
                  f"{r['misgrounding@1_ci']}")
    for k, v in res["mcnemar_R@1"].items():
        if v["only_A"] or v["only_B"]:
            print("McNemar R@1", k, v, res["flipped"][k])
    for k, v in res["mcnemar_mis@1"].items():
        if v["only_A"] or v["only_B"]:
            print("McNemar mis@1", k, v)


if __name__ == "__main__":
    main(*sys.argv[1:3])
