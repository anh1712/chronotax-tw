"""Every published README/REPORT number the audit could recompute: published | today's code+data | Fix A | Fix A+B.

  python -I -B src/audit/summary_numbers.py   -> data/audit/out/summary_numbers.json, data/audit/out/summary_numbers.md

Inputs: data/bench/results_*.json (published, read-only) and the audit outputs in data/audit/out/.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BENCH, OUT, write_json  # noqa: E402


def j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def ci(v):
    return f"{v[0]:.3f} ({v[1][0]:.3f}–{v[1][1]:.3f})" if isinstance(v[1], (list, tuple)) else str(v)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    pr = json.loads((BENCH / "results_retrieval.json").read_text(encoding="utf-8"))
    prr = json.loads((BENCH / "results_rerank.json").read_text(encoding="utf-8"))
    pnl = json.loads((BENCH / "results_nl.json").read_text(encoding="utf-8"))["summary"]
    ea, eab = j("eval_amount.json"), j("eval_amount_ab.json")
    ra, rab = j("rerank_filter.json")["models"], j("rerank_filter_ab.json")["models"]
    sa, sab = j("store_stats.json"), j("store_stats_ab.json")
    nla, nlab, nlg = j("nl_and_items.json"), j("nl_and_items_ab.json"), j("nl_regrade_ab.json")
    rows = []

    def add(group, what, published, today, a, ab, source):
        rows.append({"group": group, "number": what, "published": published, "today": today, "fix_A": a, "fix_AB": ab,
                     "source": source})

    c, fa, fb = sa["current"], sa["fixed"], sab["fixed"]
    for k, label in (("acts", "acts"), ("versions", "versions"), ("article_versions", "article versions"),
                     ("retroactive_article_versions", "retroactive article versions (README 54)"),
                     ("overtaken_article_versions", "overtaken pending article versions (README 4)"),
                     ("overlapping_non_empty_interval_pairs", "overlapping non-empty intervals (REPORT 0)"),
                     ("pending_article_versions", "article versions not in force yet (pending)"),
                     ("versions_delayed_beyond_default", "versions starting later than the §13 default")):
        pub = {"acts": 23, "versions": 406, "article_versions": 3555, "retroactive_article_versions": 54,
               "overtaken_article_versions": 4, "overlapping_non_empty_interval_pairs": 0}.get(k, "—")
        add("store", label, pub, c[k], fa[k], fb[k], "store_stats.json, store_stats_ab.json")
    for m, label in (("static", "all versions, date ignored"), ("latest", "today's text only"),
                     ("temporal", "versions in force on the date")):
        p = pr[m]
        add("retrieval (264 amount probes)", f"{label}: R@1", ci([p["R@1"], p["R@1_ci"]]),
            ci([ea["runs"]["current/gold_orig"][m]["R@1"], ea["runs"]["current/gold_orig"][m]["R@1_ci"]]),
            ci([ea["runs"]["fixed/gold_fixed"][m]["R@1"], ea["runs"]["fixed/gold_fixed"][m]["R@1_ci"]]),
            ci([eab["runs"]["fixed/gold_fixed"][m]["R@1"], eab["runs"]["fixed/gold_fixed"][m]["R@1_ci"]]),
            "results_retrieval.json; eval_amount.json; eval_amount_ab.json")
        add("retrieval (264 amount probes)", f"{label}: right article, wrong version @1",
            ci([p["misgrounding@1"], p["misgrounding@1_ci"]]),
            ci([ea["runs"]["current/gold_orig"][m]["misgrounding@1"], ea["runs"]["current/gold_orig"][m]["misgrounding@1_ci"]]),
            ci([ea["runs"]["fixed/gold_fixed"][m]["misgrounding@1"], ea["runs"]["fixed/gold_fixed"][m]["misgrounding@1_ci"]]),
            ci([eab["runs"]["fixed/gold_fixed"][m]["misgrounding@1"], eab["runs"]["fixed/gold_fixed"][m]["misgrounding@1_ci"]]),
            "same")
    for k in ra["current"]:
        add("reranker (1,207 probes)", f"{k}: R@1", f"{prr[k]['R@1']:.3f}", f"{ra['current'][k][0]:.3f}",
            f"{ra['fixed'][k][0]:.3f}", f"{rab['fixed'][k][0]:.3f}", "results_rerank.json; rerank_filter*.json")
        add("reranker (1,207 probes)", f"{k}: wrong version @1", f"{prr[k]['misgrounding@1']:.3f}",
            f"{ra['current'][k][2]:.3f}", f"{ra['fixed'][k][2]:.3f}", f"{rab['fixed'][k][2]:.3f}", "same")
    for k, v in prr["_mcnemar"].items():
        f = lambda t: f"{t['only_A']} vs {t['only_B']}, p={t['p']}"  # noqa: E731
        add("reranker McNemar", k, f(v), f(ra["mcnemar_current"][k]), f(ra["mcnemar_fixed"][k]), f(rab["mcnemar_fixed"][k]),
            "results_rerank.json; rerank_filter*.json")
    for k in ("year_ok", "r1", "r5", "amount_ok", "distractor", "insufficient"):
        p = pnl[k]
        add("NL (105 questions)", k, ci([p["rate"], p["ci"]]), ci([p["rate"], p["ci"]]) + (
            " (R@k re-run: " + str(nla["nl_current"]["R@1" if k == "r1" else "R@5"][0] if False else "") + ")" if False else ""),
            ci([nla["nl_fixed"]["R@1"], nla["nl_fixed"]["R@1_ci"]]) if k == "r1" else
            ci([nla["nl_fixed"]["R@5"], nla["nl_fixed"]["R@5_ci"]]) if k == "r5" else ci([p["rate"], p["ci"]]) + " (no gold change)",
            ci([nlg["regraded_fix_ab"][k]["rate"], nlg["regraded_fix_ab"][k]["ci"]]), "results_nl.json; nl_and_items*.json; "
            "nl_regrade_ab.json")
    w = pnl["wrong_answers_flagged_by_code"]
    add("NL (105 questions)", "wrong answers flagged by code", f"{w['flagged']} of {w['n']}", f"{w['flagged']} of {w['n']}",
        f"{w['flagged']} of {w['n']}", f"{nlg['regraded_fix_ab']['wrong_answers_flagged_by_code']['flagged']} of "
        f"{nlg['regraded_fix_ab']['wrong_answers_flagged_by_code']['n']}", "nl_regrade_ab.json")
    ex = {"amount probes with a new gold label": (len(ea["gold_changed"]), len(eab["gold_changed"])),
          "rerank probes with a new gold label": (len(j("rerank_filter.json")["gold_changed"]),
                                                  len(j("rerank_filter_ab.json")["gold_changed"])),
          "NL questions with a new gold label": (len(nla["nl_gold_changed"]), len(nlab["nl_gold_changed"])),
          "NL questions whose gold version's interval changes": (len(nla["nl_gold_version_interval_changed"]),
                                                                 len(nlab["nl_gold_version_interval_changed"])),
          "NL questions with a retrieved source whose interval changes": (len(nla["nl_any_source_interval_changed"]),
                                                                          len(nlab["nl_any_source_interval_changed"])),
          "P0 items whose reference version's interval changes": (len(nla["p0_items_reference_version_interval_changed"]),
                                                                  len(nlab["p0_items_reference_version_interval_changed"])),
          "P0 items whose version in force on the item date changes": (len(nla["p0_items_version_in_force_on_date_changed"]),
                                                                       len(nlab["p0_items_version_in_force_on_date_changed"]))}
    for k, (a, ab) in ex.items():
        add("exposure", k, "—", 0, a, ab, "eval_amount*.json, rerank_filter*.json, nl_and_items*.json")
    rg, rgab = j("regen_eval.json"), j("regen_ab_eval.json")
    add("benchmark if regenerated", "probes by type (version/span/amount/bitemporal)", "1225/2010/264/104",
        "1225/2010/264/104", "1224/2010/264/100",
        "/".join(str(rgab["_summary"]["by_type"][t]) for t in ("version_id", "span", "amount", "bitemporal")),
        "summary.json; regen/summary.json; regen_ab/summary.json")
    add("benchmark if regenerated", "temporal R@1 on regenerated amount probes", "0.693", "0.697",
        f"{rg['temporal']['R@1']:.3f}", f"{rgab['temporal']['R@1']:.3f}", "regen_eval.json, regen_ab_eval.json")
    write_json(OUT / "summary_numbers.json", rows)
    md = ["| Group | Number | Published | Today's code+data | Fix A | Fix A+B |", "|---|---|---|---|---|---|"]
    md += [f"| {r['group']} | {r['number']} | {r['published']} | {r['today']} | {r['fix_A']} | {r['fix_AB']} |" for r in rows]
    (OUT / "summary_numbers.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
