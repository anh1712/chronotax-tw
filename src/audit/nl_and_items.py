"""Impact on the 105 NL questions (TW-TaxTime-NL) and on P0's verifier items — 0 LLM calls.

  python -I -B src/audit/nl_and_items.py   -> data/audit/out/nl_and_items.json

NL: the retrieval half of the end-to-end run is re-run with the ORIGINAL answer.retrieve() (no LLM) on today's store
copy and on the corrected store, using the period stored in data/bench/results_nl.json for each question.
R@1 / R@5 must reproduce results_nl.json on today's store. The answer-level metrics (correct amount, distractor,
abstention) need the LLM and are NOT re-run; we count the questions whose gold or retrieved sources change.
P0 items (data/verifier/items.jsonl, read-only): items whose reference article version, or the version in force on
the item's date, changes in the corrected store.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BENCH, CUR_DB, FIXED_DB, OUT, ROOT, TAG, ro, write_json  # noqa: E402

import answer  # noqa: E402  original (reads .env for the LLM settings; the LLM is never called here)
from eval_retrieval import wilson  # noqa: E402
from rerank import mcnemar  # noqa: E402

IN_FORCE = "valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"


def gold_in(con, law_id, art, d):
    r = con.execute(f"SELECT id, deleted FROM article_version WHERE law_id=? AND article_no=? AND {IN_FORCE} "
                    "ORDER BY valid_from DESC, id DESC", (law_id, art, d, d)).fetchall()
    return (None if r[0][1] else r[0][0]) if r else None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cur, fix = ro(CUR_DB), ro(FIXED_DB)
    changed_ids = {c["id"] for c in json.loads((OUT / f"cmp_current_vs_fixed{TAG}.json").read_text(encoding="utf-8"))["changed"]
                   if {"valid_from", "valid_to", "pending"} & set(c)}
    # ---- NL ----
    gen = {r["probe_id"]: r for r in map(json.loads, (BENCH / "tw_taxtime_nl.jsonl").open(encoding="utf-8"))}
    pub = json.loads((BENCH / "results_nl.json").read_text(encoding="utf-8"))
    items = [i for i in pub["items"] if "infra" not in i]
    out = {"nl_questions": len(items)}
    per = {"current": [], "fixed": []}
    for tag, db in (("current", CUR_DB), ("fixed", FIXED_DB)):
        answer.DB = db
        for it in items:
            q = gen[it["id"]]
            con = cur if tag == "current" else fix
            g = q["gold_version_id"] if tag == "current" else gold_in(con, q["law_id"], q["article"], q["as_of"])
            hits = answer.retrieve(q["question"], it["period"]["as_of"], None)
            ids = [h["id"] for h in hits]
            per[tag].append({"id": it["id"], "gold": g, "ids": ids, "r1": bool(ids) and ids[0] == g, "r5": g in ids})
    rep = sum(a["r1"] == b["r1"] and a["r5"] == b["r5"] for a, b in zip(per["current"], items))
    out["nl_reproduced_r1_r5_on_current"] = f"{rep}/{len(items)}"
    for tag in per:
        n = len(per[tag])
        k1, k5 = sum(x["r1"] for x in per[tag]), sum(x["r5"] for x in per[tag])
        out[f"nl_{tag}"] = {"R@1": round(k1 / n, 3), "R@1_ci": wilson(k1, n), "R@5": round(k5 / n, 3), "R@5_ci": wilson(k5, n)}
    out["nl_mcnemar_R@1_fixed_vs_current"] = mcnemar([x["r1"] for x in per["fixed"]], [x["r1"] for x in per["current"]])
    out["nl_mcnemar_R@5_fixed_vs_current"] = mcnemar([x["r5"] for x in per["fixed"]], [x["r5"] for x in per["current"]])
    out["nl_gold_changed"] = [a["id"] for a, b in zip(per["current"], per["fixed"]) if a["gold"] != b["gold"]]
    out["nl_sources_changed"] = [a["id"] for a, b in zip(per["current"], per["fixed"]) if a["ids"] != b["ids"]]
    out["nl_gold_version_interval_changed"] = [a["id"] for a in per["current"] if a["gold"] in changed_ids]
    out["nl_any_source_interval_changed"] = [a["id"] for a in per["current"] if set(a["ids"]) & changed_ids]
    # ---- P0 verifier items ----
    vi = [json.loads(l) for l in (ROOT / "data" / "verifier" / "items.jsonl").open(encoding="utf-8")]
    ref_changed, gold_changed, cited_changed = [], [], []
    for it in vi:
        srcs = [s for s in (it.get("reference") or {}).get("sources", []) if s.get("kind") == "article_version"]
        ids = {int(s["source_id"]) for s in srcs if str(s.get("source_id", "")).isdigit()}
        if ids & changed_ids:
            ref_changed.append(it["item_id"])
        cited = it.get("cited") or {}
        cid = cited.get("source_id") if isinstance(cited, dict) else None
        if cid and str(cid).isdigit() and int(cid) in changed_ids:
            cited_changed.append(it["item_id"])
        d = (it.get("period") or {}).get("as_of")
        if d and it.get("law_id") and it.get("article"):
            if gold_in(cur, it["law_id"], it["article"], d) != gold_in(fix, it["law_id"], it["article"], d):
                gold_changed.append(it["item_id"])
    out["p0_items"] = len(vi)
    out["p0_items_reference_version_interval_changed"] = ref_changed
    out["p0_items_cited_version_interval_changed"] = cited_changed
    out["p0_items_version_in_force_on_date_changed"] = gold_changed
    write_json(OUT / f"nl_and_items{TAG}.json", out)
    for k, v in out.items():
        print(f"{k}: {v if not isinstance(v, list) else (len(v), v[:12])}")


if __name__ == "__main__":
    main()
