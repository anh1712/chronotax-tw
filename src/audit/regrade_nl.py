"""Re-grade TW-TaxTime-NL (data/bench/results_nl.json) after the date fix — 0 LLM calls.

  python -I -B src/audit/regrade_nl.py   -> data/bench/results_nl.json (pre-fix copy: data/bench/_prefix_2026-10-26/)

The LLM answers are NOT regenerated. For every evaluated question:
  r1 / r5        recomputed with the ORIGINAL answer.retrieve() on the corrected data/lawtw.db, with the period stored
                 in the pre-fix results (the retrieval half of nl_bench.evaluate)
  amount_ok /    unchanged, except for questions whose gold was relabelled (data/bench/tw_taxtime_nl.jsonl,
  distractor     "relabel_2026_10_26"): there the new gold amount is exactly the old temporal distractor and the new
                 distractor is the old gold amount (checked), so the two stored flags swap.
Summary block = the same computation as nl_bench.evaluate().
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BENCH  # noqa: E402

import answer  # noqa: E402  original (no LLM call is made)
from eval_retrieval import wilson  # noqa: E402

PRE = BENCH / "_prefix_2026-10-26"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    pub = json.loads((PRE / "results_nl.json").read_text(encoding="utf-8"))
    gen = {r["probe_id"]: r for r in map(json.loads, (BENCH / "tw_taxtime_nl.jsonl").open(encoding="utf-8"))}
    rows = [r for r in gen.values() if r.get("question") and not r.get("rejected")]
    out, swapped, r_changed = [], [], []
    for it in pub["items"]:
        if "infra" in it:
            out.append(it)
            continue
        q = gen[it["id"]]
        hits = answer.retrieve(q["question"], it["period"]["as_of"], None)
        ids = [h["id"] for h in hits]
        new = {**it, "r1": bool(ids) and ids[0] == q["gold_version_id"], "r5": q["gold_version_id"] in ids}
        if (new["r1"], new["r5"]) != (it["r1"], it["r5"]):
            r_changed.append(it["id"])
        rel = q.get("relabel_2026_10_26")
        if rel:
            assert q["gold_amount"] == rel["temporal_distractor"] and q["temporal_distractor"] == rel["gold_amount"], it["id"]
            new["amount_ok"], new["distractor"] = it["distractor"], it["amount_ok"]
            swapped.append(it["id"])
        out.append(new)
    ok = [o for o in out if "infra" not in o]
    n = len(ok)
    summ = {"questions": len(rows), "evaluated": n, "infra_errors": len(out) - n}
    for k in ("year_ok", "r1", "r5", "amount_ok", "distractor", "all_verified", "insufficient"):
        c = sum(bool(o.get(k)) for o in ok)
        summ[k] = {"rate": round(c / n, 3) if n else None, "ci": wilson(c, n)}
    wrong = [o for o in ok if not o["amount_ok"] and not o["insufficient"]]
    summ["wrong_answers_flagged_by_code"] = {"n": len(wrong), "flagged": sum(not o["all_verified"] for o in wrong)}
    note = {"date": "2026-10-26", "llm_calls": 0,
            "method": "grades re-derived after the effective-date fix (docs/AUDIT_DATES.md); answers not regenerated; "
                      "r1/r5 re-run with answer.retrieve on the corrected store; amount_ok/distractor swapped for "
                      "relabelled questions (new gold = old distractor, checked)",
            "relabelled_questions": swapped, "retrieval_outcome_changed": r_changed,
            "pre_fix_file": "data/bench/_prefix_2026-10-26/results_nl.json"}
    (BENCH / "results_nl.json").write_text(json.dumps({"summary": summ, "items": out, "regraded_2026_10_26": note},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    print("swapped:", swapped, "r1/r5 changed:", r_changed)


if __name__ == "__main__":
    main()
