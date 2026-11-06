"""Retrieval on TW-MedTime vs TW-TaxTime with the SAME code (eval_retrieval.run, unchanged), side by side.

  python -I src/med/eval_med.py   -> data/med/results/retrieval_side_by_side.json

For each domain and probe type (amount = the ChronoTax headline; span = changed wording) and each index
  static   (all versions, date ignored) · latest (today's text only) · temporal (versions in force on the date):
R@1, R@5, wrong version @1 (= eval_retrieval's misgrounding@1: top hit is the right ARTICLE but the wrong VERSION),
Wilson 95% CI. eval_retrieval.run is called once per probe, so static vs temporal can be compared with a paired exact
McNemar test; tax vs medical rates are compared with Newcombe's 95% interval for a difference of two proportions.
The tax store (data/lawtw.db) and its probes (data/bench/tw_taxtime_v0.jsonl) are opened READ-ONLY;
eval_retrieval.main() is never called (it would overwrite data/bench/results_retrieval.json).
Extra: the medical probes are also run against medtw_taxparser.db (the medical store built with the unchanged tax
rules); gold is matched by (law, article, first LY version, text), because row ids differ between the two stores.
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402
from medcfg import BENCH, DB, MED, RESULTS, TAX_BENCH, TAX_DB, write_atomic  # noqa: E402
import eval_retrieval  # noqa: E402  original (run, wilson, MODES)

TAXPARSER_DB = MED / "medtw_taxparser.db"
MODES = list(eval_retrieval.MODES)


def ro(p: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def per_probe(con, items, mode) -> list[tuple[int, int, int]]:
    """(hit@1, hit@5, wrong-version@1) for each probe, by calling the original eval_retrieval.run on one probe."""
    out = []
    for it in items:
        r = eval_retrieval.run(con, [it], mode)
        out.append((int(r["R@1"] == 1.0), int(r["R@5"] == 1.0), int(r["misgrounding@1"] == 1.0)))
    return out


def summarize(rows) -> dict:
    n = len(rows)
    k1, k5, km = (sum(r[i] for r in rows) for i in range(3))
    return {"n": n, "R@1": round(k1 / n, 3) if n else None, "R@1_ci": eval_retrieval.wilson(k1, n),
            "R@5": round(k5 / n, 3) if n else None, "wrong_version@1": round(km / n, 3) if n else None,
            "wrong_version@1_ci": eval_retrieval.wilson(km, n), "k_R@1": k1, "k_wrong_version@1": km}


def mcnemar(a: list[int], b: list[int]) -> dict:
    """Exact two-sided McNemar (binomial on discordant pairs)."""
    b01 = sum(x == 0 and y == 1 for x, y in zip(a, b))
    b10 = sum(x == 1 and y == 0 for x, y in zip(a, b))
    n = b01 + b10
    if n == 0:
        return {"a_only": b10, "b_only": b01, "p": 1.0}
    k = min(b01, b10)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"a_only": b10, "b_only": b01, "p": p}


def newcombe(k1: int, n1: int, k2: int, n2: int) -> dict:
    """Difference p1 - p2 with Newcombe's hybrid score 95% interval (from the two Wilson intervals)."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = eval_retrieval.wilson(k1, n1)
    l2, u2 = eval_retrieval.wilson(k2, n2)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return {"diff": round(d, 3), "ci": (round(lo, 3), round(hi, 3))}


def domain(con, items) -> dict:
    res, raw = {}, {}
    for m in MODES:
        raw[m] = per_probe(con, items, m)
        res[m] = summarize(raw[m])
    res["paired_R@1_static_vs_temporal"] = mcnemar([r[0] for r in raw["static"]], [r[0] for r in raw["temporal"]])
    res["paired_R@1_latest_vs_temporal"] = mcnemar([r[0] for r in raw["latest"]], [r[0] for r in raw["temporal"]])
    return res, raw


def flagged_keys(con) -> set:
    """(law, article) with a paragraph-level exception, a pending text or a pending gap: dates are approximate there."""
    keys = {tuple(r) for r in con.execute("SELECT law_id, article_no FROM partial_commencement")}
    keys |= {tuple(r) for r in con.execute("SELECT law_id, article_no FROM pending_article")}
    keys |= {tuple(r) for r in con.execute("SELECT law_id, article_no FROM article_version WHERE flag IS NOT NULL")}
    return keys


def main() -> None:
    med_items = [json.loads(line) for line in (BENCH / "tw_medtime_v0.jsonl").open(encoding="utf-8")]
    tax_items = [json.loads(line) for line in TAX_BENCH.open(encoding="utf-8")]
    med, tax, tp = ro(DB), ro(TAX_DB), ro(TAXPARSER_DB)
    flagged = flagged_keys(med)
    out = {"probes": {"medical": {}, "tax": {}}, "results": {}}
    for dom, items in (("medical", med_items), ("tax", tax_items)):
        for t in ("version_id", "amount", "span", "bitemporal"):
            out["probes"][dom][t] = sum(i["type"] == t for i in items)
    raws = {}
    for ptype in ("amount", "span"):
        mi = [i for i in med_items if i["type"] == ptype]
        ti = [i for i in tax_items if i["type"] == ptype]
        out["results"][f"medical_{ptype}"], raws[("medical", ptype)] = domain(med, mi)
        out["results"][f"tax_{ptype}"], raws[("tax", ptype)] = domain(tax, ti)
        clean = [k for k, i in enumerate(mi) if (i["law_id"], i["article"]) not in flagged]
        out["results"][f"medical_{ptype}_unflagged"] = {
            m: summarize([raws[("medical", ptype)][m][k] for k in clean]) for m in MODES}
        # does the tax finding replicate? difference in wrong-version@1 of the static index, medical - tax
        a, b = out["results"][f"medical_{ptype}"]["static"], out["results"][f"tax_{ptype}"]["static"]
        out["results"][f"static_wrong_version_medical_minus_tax_{ptype}"] = newcombe(
            a["k_wrong_version@1"], a["n"], b["k_wrong_version@1"], b["n"])
    # per act (medical, static index, amount+span): where does the wrong version come from?
    per_act = {}
    for ptype in ("amount", "span"):
        mi = [i for i in med_items if i["type"] == ptype]
        for i, r in zip(mi, raws[("medical", ptype)]["static"]):
            d = per_act.setdefault(i["law_id"], {"law": i["law"], "law_en": i["law_en"], "n": 0, "wrong_version": 0, "hit": 0})
            d["n"] += 1
            d["wrong_version"] += r[2]
            d["hit"] += r[0]
    out["results"]["medical_static_by_act_amount_plus_span"] = per_act

    # why do the domains differ? span probes know their distractor version: split the static wrong-version rate by
    # whether the NEWER of the two versions comes from a whole-act revision (全文修正: wording and numbering change a lot)
    for dom, con, items in (("medical", med, med_items), ("tax", tax, tax_items)):
        act = {r[0]: r[1] for r in con.execute("SELECT ly_version, action FROM version")}
        meta = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, first_ly_version, valid_from FROM article_version")}
        si = [i for i in items if i["type"] == "span"]
        split = {"full_text_revision": [0, 0], "partial_amendment": [0, 0]}
        for i, r in zip(si, raws[(dom, "span")]["static"]):
            g, o = meta[i["gold_version_id"]], meta[i["temporal_distractor_id"]]
            newer = g if g[1] >= o[1] else o
            key = "full_text_revision" if "全文" in (act.get(newer[0]) or "") else "partial_amendment"
            split[key][0] += 1
            split[key][1] += r[2]
        out["results"][f"{dom}_span_static_wrong_version_by_change_kind"] = {
            k: {"n": n, "wrong_version@1": round(w / n, 3) if n else None, "ci": eval_retrieval.wilson(w, n)}
            for k, (n, w) in split.items()}

    # the unchanged tax rules on medical data: same probes, gold matched by (law, article, first LY version, text)
    gold = {r[0]: (r[1], r[2], r[3], r[4]) for r in med.execute(
        "SELECT id, law_id, article_no, first_ly_version, text FROM article_version")}
    tp_ids = {}
    for r in tp.execute("SELECT id, law_id, article_no, first_ly_version, text FROM article_version WHERE deleted=0"):
        tp_ids.setdefault((r[1], r[2], r[3], r[4]), r[0])
    tpres = {}
    for ptype in ("amount", "span"):
        mapped = []
        for i in (i for i in med_items if i["type"] == ptype):
            mapped.append({**i, "gold_version_id": tp_ids.get(gold[i["gold_version_id"]], -1)})
        tpres[ptype] = {m: summarize(per_probe(tp, mapped, m)) for m in ("temporal",)}
        tpres[ptype]["gold_text_missing_in_tax_parser_store"] = sum(m["gold_version_id"] == -1 for m in mapped)
    # version_id probes: which text is in force on the date, by direct lookup (no retrieval) in each store
    sql = ("SELECT id FROM article_version WHERE law_id=? AND article_no=? AND deleted=0 AND valid_from<=? "
           "AND (valid_to IS NULL OR valid_to>?)")
    vi = [i for i in med_items if i["type"] == "version_id"]
    ok_med = ok_tp = 0
    wrong_tp = []
    for i in vi:
        a = med.execute(sql, (i["law_id"], i["article"], i["as_of"], i["as_of"])).fetchone()
        b = tp.execute(sql, (i["law_id"], i["article"], i["as_of"], i["as_of"])).fetchone()
        ok_med += bool(a) and a[0] == i["gold_version_id"]
        good = bool(b) and b[0] == tp_ids.get(gold[i["gold_version_id"]])
        ok_tp += good
        if not good:
            wrong_tp.append((i["law"], i["article"], i["as_of"]))
    by_law = {}
    for law, _, _ in wrong_tp:
        by_law[law] = by_law.get(law, 0) + 1
    tpres["version_id_lookup"] = {
        "n": len(vi), "chronomed_correct": ok_med, "tax_parser_correct": ok_tp,
        "tax_parser_wrong": len(vi) - ok_tp, "tax_parser_wrong_rate": round((len(vi) - ok_tp) / len(vi), 3),
        "tax_parser_wrong_ci": eval_retrieval.wilson(len(vi) - ok_tp, len(vi)), "tax_parser_wrong_by_act": by_law}
    out["results"]["medical_probes_on_tax_parser_store"] = tpres
    # the published ChronoTax numbers, for reference (read-only)
    pub = MED.parent / "bench" / "results_retrieval.json"
    out["published_chronotax_results_retrieval_json"] = json.loads(pub.read_text(encoding="utf-8")) if pub.exists() else None
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_atomic(RESULTS / "retrieval_side_by_side.json", json.dumps(out, ensure_ascii=False, indent=1))

    print("probes", out["probes"])
    for key in ("tax_amount", "medical_amount", "medical_amount_unflagged", "tax_span", "medical_span", "medical_span_unflagged"):
        for m in MODES:
            r = out["results"][key][m]
            print(f"{key:26s} {m:9s} n={r['n']:5d} R@1={r['R@1']} {r['R@1_ci']} R@5={r['R@5']} "
                  f"wrong-version@1={r['wrong_version@1']} {r['wrong_version@1_ci']}")
    for key in ("medical_amount", "medical_span", "tax_amount", "tax_span"):
        print(key, "McNemar static vs temporal:", out["results"][key]["paired_R@1_static_vs_temporal"])
    for p in ("amount", "span"):
        print("static wrong-version medical - tax", p, out["results"][f"static_wrong_version_medical_minus_tax_{p}"])
    print("tax-parser store:", json.dumps(tpres, ensure_ascii=False)[:900])
    for dom in ("medical", "tax"):
        print(dom, "span static wrong-version by change kind:", out["results"][f"{dom}_span_static_wrong_version_by_change_kind"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
