"""Reranker study, "with date filter" column (1,207 held-out probes, data/bench/rerank_test.jsonl, read-only).

  python -I -B src/audit/rerank_filter.py [--score]   -> data/audit/out/rerank_filter.json

1. Reproduce bm25 / date filter → bm25 from the stored candidates with the ORIGINAL rerank.metrics / in_force.
2. Check the stored candidate intervals against today's store (by article-version id).
3. Corrected store: candidate intervals and passages ("valid_from~valid_to article window", built with the ORIGINAL
   rerank.passage) are rebuilt from data/audit/lawtw_fixed.db; gold = version in force on the probe date there.
   A probe is AFFECTED if its gold, or any candidate's interval, changes. Unaffected probes have identical inputs, so
   every system's outcome on them is unchanged by construction.
4. --score: affected probes are re-scored with each cross-encoder (zero-shot BAAI/bge-reranker-base if cached locally,
   data/models/rr-*), old and new passages, with the ORIGINAL rerank.score (GPU fp16, as published).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BENCH, CUR_DB, FIXED_DB, OUT, TAG, ro, write_json  # noqa: E402

import rerank  # noqa: E402  original: metrics, in_force, passage, score, mcnemar

IN_FORCE = "valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"


def gold_in(con, law_id, art, d):
    r = con.execute(f"SELECT id, deleted FROM article_version WHERE law_id=? AND article_no=? AND {IN_FORCE} "
                    "ORDER BY valid_from DESC, id DESC", (law_id, art, d, d)).fetchall()
    return (None if r[0][1] else r[0][0]) if r else None


def main(do_score: bool) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = [json.loads(l) for l in (BENCH / "rerank_test.jsonl").open(encoding="utf-8")]
    probes = {p["id"]: p for p in map(json.loads, (BENCH / "tw_taxtime_v0.jsonl").open(encoding="utf-8"))}
    cur, fix = ro(CUR_DB), ro(FIXED_DB)
    res = {"n": len(rows), "published": {k: v["R@1"] for k, v in json.loads(
        (BENCH / "results_rerank.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}}
    m_bm25 = rerank.metrics(rows, lambda r: r["cands"])
    m_filt = rerank.metrics(rows, lambda r: [c for c in r["cands"] if rerank.in_force(c, r["as_of"])])
    res["reproduced_from_stored"] = {"bm25 (static)": m_bm25["R@1"], "date filter → bm25": m_filt["R@1"]}
    # stored intervals vs today's store
    mism = 0
    for r in rows:
        for c in r["cands"]:
            v = cur.execute("SELECT valid_from, valid_to FROM article_version WHERE id=?", (c["id"],)).fetchone()
            mism += (v["valid_from"], v["valid_to"]) != (c["valid_from"], c["valid_to"])
    res["stored_intervals_differing_from_current_store"] = mism
    # corrected inputs
    fixed_rows, affected = [], []
    for r in rows:
        p = probes[r["id"]]
        ctx = p["context"]
        g = gold_in(fix, p["law_id"], r["article"], r["as_of"])
        cands, changed = [], g != r["gold"]
        for c in r["cands"]:
            v = fix.execute("SELECT * FROM article_version WHERE id=?", (c["id"],)).fetchone()
            nc = {**c, "valid_from": v["valid_from"], "valid_to": v["valid_to"], "p": rerank.passage(v, ctx)}
            changed |= (nc["valid_from"], nc["valid_to"]) != (c["valid_from"], c["valid_to"])
            cands.append(nc)
        fr = {**r, "gold": g if g is not None else -1, "cands": cands}
        fixed_rows.append(fr)
        if changed:
            affected.append(r["id"])
    res["affected_probes"] = affected
    res["affected_by_type"] = {t: sum(probes[i]["type"] == t for i in affected) for t in ("amount", "span")}
    res["gold_changed"] = [{"id": r["id"], "old": r["gold"], "new": f["gold"]} for r, f in zip(rows, fixed_rows)
                           if r["gold"] != f["gold"]]
    f_bm25 = rerank.metrics(fixed_rows, lambda r: r["cands"])
    f_filt = rerank.metrics(fixed_rows, lambda r: [c for c in r["cands"] if rerank.in_force(c, r["as_of"])])
    res["fixed"] = {"bm25 (static)": [f_bm25["R@1"], f_bm25["R@1_ci"], f_bm25["misgrounding@1"]],
                    "date filter → bm25": [f_filt["R@1"], f_filt["R@1_ci"], f_filt["misgrounding@1"]]}
    res["current"] = {"bm25 (static)": [m_bm25["R@1"], m_bm25["R@1_ci"], m_bm25["misgrounding@1"]],
                      "date filter → bm25": [m_filt["R@1"], m_filt["R@1_ci"], m_filt["misgrounding@1"]]}
    res["mcnemar"] = {"date filter → bm25: fixed vs current": rerank.mcnemar(f_filt["_hits"], m_filt["_hits"]),
                      "bm25 (static): fixed vs current": rerank.mcnemar(f_bm25["_hits"], m_bm25["_hits"])}
    res["affected_detail"] = []
    idx = {r["id"]: i for i, r in enumerate(rows)}
    for pid in affected:
        i = idx[pid]
        res["affected_detail"].append({"id": pid, "type": probes[pid]["type"], "law": probes[pid]["law"],
                                       "article": rows[i]["article"], "as_of": rows[i]["as_of"],
                                       "gold_old": rows[i]["gold"], "gold_new": fixed_rows[i]["gold"],
                                       "filter_bm25_hit_old": m_filt["_hits"][i], "filter_bm25_hit_new": f_filt["_hits"][i],
                                       "static_bm25_hit_old": m_bm25["_hits"][i], "static_bm25_hit_new": f_bm25["_hits"][i]})
    if do_score:
        res["models"] = score_models(rows, fixed_rows, affected, idx)
    write_json(OUT / f"rerank_filter{TAG}.json", res)
    print({k: v for k, v in res.items() if k not in ("affected_detail", "published", "models", "affected_probes")})
    if do_score:
        print(json.dumps({k: v for k, v in res["models"].items() if k != "changed_probes"}, ensure_ascii=False, indent=1))
        print("changed probes:", res["models"]["changed_probes"])


def score_models(rows, fixed_rows, affected, idx) -> dict:
    """All 1,207 probes scored with the ORIGINAL rerank.score (GPU fp16, as published) on today's inputs (reproduces
    results_rerank.json); affected probes scored again on corrected inputs. rerank.score scores one probe per batch,
    so an unaffected probe (identical inputs) keeps its score. Systems and McNemar pairs = rerank.evaluate()."""
    import os
    import torch
    systems = {}
    zs = Path(os.environ.get("HF_HOME", "")) / "hub" / "models--BAAI--bge-reranker-base"
    if zs.exists():
        systems["zero-shot"] = rerank.BASE
    for mix in ("bm25", "temporal", "mixed"):
        if (rerank.MODELS / f"rr-{mix}").exists():
            systems[f"fine-tuned/{mix}"] = str(rerank.MODELS / f"rr-{mix}")
    aff = [idx[i] for i in affected]
    hits = {"current": {}, "fixed": {}}
    out = {"systems": list(systems), "zero_shot_cache": str(zs)}
    rank = lambda r, s: [c for _, c in sorted(zip(s, r["cands"]), key=lambda x: -x[0])]  # noqa: E731
    for tag, rr in (("current", rows), ("fixed", fixed_rows)):
        hits[tag]["bm25 (static)"] = rerank.metrics(rr, lambda r: r["cands"])
        hits[tag]["date filter → bm25"] = rerank.metrics(rr, lambda r: [c for c in r["cands"] if rerank.in_force(c, r["as_of"])])
    for name, path in systems.items():
        torch.cuda.reset_peak_memory_stats()
        s_cur = rerank.score(path, rows)
        s_aff = rerank.score(path, [fixed_rows[i] for i in aff])
        s_fix = list(s_cur)
        for i, s in zip(aff, s_aff):
            s_fix[i] = s
        out[f"gpu_peak_mb/{name}"] = round(torch.cuda.max_memory_allocated() / 2**20)
        for tag, rr, sc in (("current", rows, s_cur), ("fixed", fixed_rows, s_fix)):
            sm = {r["id"]: s for r, s in zip(rr, sc)}
            hits[tag][f"{name} (static)"] = rerank.metrics(rr, lambda r: rank(r, sm[r["id"]]))
            hits[tag][f"date filter → {name}"] = rerank.metrics(
                rr, lambda r: [c for c in rank(r, sm[r["id"]]) if rerank.in_force(c, r["as_of"])])
        del s_cur, s_aff
        torch.cuda.empty_cache()
    pairs = [("fine-tuned/temporal (static)", "fine-tuned/bm25 (static)"),
             ("fine-tuned/temporal (static)", "fine-tuned/mixed (static)"),
             ("fine-tuned/bm25 (static)", "zero-shot (static)"),
             ("date filter → fine-tuned/temporal", "date filter → bm25"),
             ("date filter → bm25", "fine-tuned/temporal (static)")]
    for tag in ("current", "fixed"):
        out[tag] = {k: [v["R@1"], v["R@1_ci"], v["misgrounding@1"]] for k, v in hits[tag].items()}
        out[f"mcnemar_{tag}"] = {f"{a} vs {b}": rerank.mcnemar(hits[tag][a]["_hits"], hits[tag][b]["_hits"])
                                 for a, b in pairs if a in hits[tag] and b in hits[tag]}
    out["fixed_vs_current_same_system"] = {k: rerank.mcnemar(hits["fixed"][k]["_hits"], hits["current"][k]["_hits"])
                                           for k in hits["current"]}
    out["changed_probes"] = {k: [rows[i]["id"] for i in range(len(rows))
                                 if hits["fixed"][k]["_hits"][i] != hits["current"][k]["_hits"][i]] for k in hits["current"]}
    return out


if __name__ == "__main__":
    main("--score" in sys.argv)
