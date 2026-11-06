"""Store statistics with ONE set of definitions for three stores, plus commencement-form statistics for both domains.

  python -I src/med/stats_med.py      -> data/med/results/store_stats.json

Stores: medtw.db (ChronoMed, extended rules) · medtw_taxparser.db (original pipeline on the same medical data) ·
data/lawtw.db (ChronoTax, opened READ-ONLY, restricted to the 23 acts of src/registry.py).
Definitions (same SQL for all): article version = article_version row with deleted=0 (ChronoTax's "3,555");
delayed = starts later than the 中央法規標準法 §13 default (promulgation + 2 days); retroactive = starts before
promulgation; overtaken = overtaken=1 (pending text replaced before it ever applied).
"""
import datetime as dt
import json
import re
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402
from medcfg import DB, MED, RESULTS, ROOT, TAX_DB, write_atomic  # noqa: E402
import build_db  # noqa: E402  original (match_versions)
import effect_rules  # noqa: E402  original
import moj_history  # noqa: E402  original
import moj_med  # noqa: E402
import registry  # noqa: E402  original (tax act list, read-only)
import registry_med  # noqa: E402

TAXPARSER_DB = MED / "medtw_taxparser.db"
TAX_RAW = ROOT / "data" / "raw"  # read-only


def ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def store_stats(path: Path, law_ids: list[str]) -> dict:
    con = ro(path)
    ph = ",".join("?" * len(law_ids))
    q = lambda sql, *a: con.execute(sql.replace("{L}", ph), (*law_ids, *a)).fetchall()  # noqa: E731
    one = lambda sql: q(sql)[0][0]  # noqa: E731
    vers = q("SELECT law_id, promulgated, effective, effective_basis FROM version WHERE law_id IN ({L})")
    delays, n_delayed, n_retro, n_pending = [], 0, 0, 0
    for _, p, e, b in vers:
        if p is None:
            continue
        if e is None:
            n_pending += 1
            continue
        d = (dt.date.fromisoformat(e) - dt.date.fromisoformat(p)).days
        if d > 2:
            n_delayed += 1
            delays.append(d)
        if d < 0:
            n_retro += 1
    art_delays = [((dt.date.fromisoformat(f) - dt.date.fromisoformat(p)).days) for f, p in
                  q("SELECT valid_from, published FROM article_version WHERE law_id IN ({L}) AND deleted=0 AND published IS NOT NULL")]
    per_article = one("SELECT count(*) FROM article_version WHERE law_id IN ({L}) AND deleted=0 AND (from_basis LIKE "
                      "'commencement%' OR from_basis LIKE 'history%' OR from_basis='moj_entry_without_ly_version')")
    out = {
        "acts": one("SELECT count(*) FROM law WHERE law_id IN ({L})"),
        "versions": len(vers),
        "versions_unmatched_ly_date_fallback": sum(b == "ly_date_fallback" for *_, b in vers),
        "versions_unknown_date_using_promulgation": sum(b == "unknown_using_promulgation" for *_, b in vers),
        "versions_pending_no_date": n_pending,
        "versions_delayed_commencement": n_delayed,
        "versions_retroactive": n_retro,
        "version_delay_days_median": statistics.median(delays) if delays else None,
        "version_delay_days_max": max(delays) if delays else None,
        "versions_delay_ge_180d": sum(d >= 180 for d in delays),
        "version_basis": dict(q("SELECT effective_basis, count(*) FROM version WHERE law_id IN ({L}) GROUP BY 1")),
        "articles": one("SELECT count(*) FROM (SELECT DISTINCT law_id, article_no FROM article_version WHERE law_id IN ({L}))"),
        "article_versions": one("SELECT count(*) FROM article_version WHERE law_id IN ({L}) AND deleted=0"),
        "tombstones": one("SELECT count(*) FROM article_version WHERE law_id IN ({L}) AND deleted=1"),
        "article_versions_retroactive": one("SELECT count(*) FROM article_version WHERE law_id IN ({L}) AND deleted=0 AND retro=1"),
        "article_versions_delayed": sum(d > 2 for d in art_delays),
        "article_versions_delay_ge_180d": sum(d >= 180 for d in art_delays),
        "article_versions_overtaken": one("SELECT count(*) FROM article_version WHERE law_id IN ({L}) AND overtaken=1"),
        "article_versions_zero_length": one("SELECT count(*) FROM article_version WHERE law_id IN ({L}) AND deleted=0 "
                                            "AND valid_to=valid_from"),
        "article_versions_with_per_article_date": per_article,
        "article_from_basis": dict(q("SELECT from_basis, count(*) FROM article_version WHERE law_id IN ({L}) AND deleted=0 GROUP BY 1")),
        "first_year": one("SELECT min(substr(ly_date,1,4)) FROM version WHERE law_id IN ({L})"),
        "last_ly_date": one("SELECT max(ly_date) FROM version WHERE law_id IN ({L})"),
    }
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "pending_article" in tables:
        out["pending_articles"] = q("SELECT law_id, article_no, ly_version, full_text_revision FROM pending_article WHERE law_id IN ({L})")
        out["partial_commencement_rows"] = one("SELECT count(*) FROM partial_commencement WHERE law_id IN ({L})")
        out["article_versions_flagged_partial"] = one("SELECT count(*) FROM article_version WHERE law_id IN ({L}) AND flag LIKE '%partial%'")
        out["pending_gap_rows"] = one("SELECT count(*) FROM article_version WHERE law_id IN ({L}) AND flag='pending_gap'")
        out["rule_conflicts"] = one("SELECT count(*) FROM rule_conflict WHERE law_id IN ({L})")
    return out


def history_stats(pages: dict[str, str], ly_meta: dict[str, dict]) -> dict:
    """Commencement forms in the MOJ histories of one domain; original vs extended parser, and LY<->MOJ matching."""
    n = diff = rel = orders = artrules = partial = pending = 0
    unparsed, delays, moj_wo_ly, diffs, delayed = [], [], 0, [], []
    for lid, page in pages.items():
        a, b = moj_history.parse(page), moj_med.parse(page)
        for x, y in zip(a, b):
            n += 1
            if x["effective"] != y["effective"]:
                diff += 1
                diffs.append((lid, y["no"], y["promulgated"], x["effective"], y["effective"]))
            rel += any(c in y["commencement_text"] for c in ("公布後", "公布日起", "發布後")) and "施行" in y["commencement_text"]
            orders += y["n_orders"] > 0
            artrules += bool(y["rules"])
            partial += bool(y["partial"])
            pending += bool(y["pending_refs"])
            unparsed += [(lid, y["no"], u[:80]) for u in y["unparsed"]]
            if y["effective"]:
                d = (dt.date.fromisoformat(y["effective"]) - dt.date.fromisoformat(y["promulgated"])).days
                delays.append(d)
                if d > 2:
                    delayed.append((lid, y["no"], y["promulgated"], y["effective"], d, y["effective_basis"]))
        if lid in ly_meta:
            pairs = build_db.match_versions(ly_meta[lid]["versions"], [e for e in b if e["is_promulgation"]])
            used = {m["no"] for _, m in pairs if m}
            moj_wo_ly += sum(e["no"] not in used for e in b if e["is_promulgation"])
    dl = [d for d in delays if d > 2]
    return {"moj_entries": n, "entries_date_differs_original_vs_extended": diff,
            "entries_relative_commencement": rel, "entries_with_executive_yuan_order": orders,
            "entries_with_per_article_or_chapter_rules": artrules, "entries_with_paragraph_level_exceptions": partial,
            "entries_with_still_pending_articles": pending, "unparsed_clauses": unparsed,
            "entries_delayed_beyond_default": len(dl), "share_delayed": round(len(dl) / n, 3) if n else None,
            "delay_days_median_of_delayed": statistics.median(dl) if dl else None,
            "entries_delay_ge_180d": sum(d >= 180 for d in dl), "moj_entries_without_ly_version": moj_wo_ly,
            "differences": diffs, "delayed_entries": delayed}


def commencement_article_stats(raw_ly: Path, law_ids: list[str]) -> dict:
    """Original effect_rules on each act's latest commencement article: rules found and sentences left unparsed."""
    rules = unparsed = 0
    rel_skipped, details = 0, []
    for lid in law_ids:
        meta = json.loads((raw_ly / lid / "_law.json").read_text(encoding="utf-8"))
        last = sorted(meta["versions"], key=lambda v: v["日期"])[-1]
        rows = json.loads((raw_ly / lid / (last["版本編號"].split(":", 1)[1] + ".json")).read_text(encoding="utf-8"))
        comm = effect_rules.find_commencement(rows)
        if not comm:
            continue
        p = effect_rules.parse(comm)
        rules += len(p["rules"])
        unparsed += len(p["unparsed"])
        # sentences with a relative date and no amendment date are skipped silently by the original parser
        for s in re.split(r"[。；]", comm.replace("　", "").replace("\n", "")):
            if re.search(r"(?:公布|發布)(?:後|日起)[〇零一二三四五六七八九十百\d]+(?:年|個月|日)", s) and not effect_rules.AMEND_RX.search(s):
                rel_skipped += 1
        details.append((lid, len(p["rules"]), p["unparsed"]))
    return {"rules": rules, "unparsed_sentences": unparsed, "relative_sentences_skipped_silently": rel_skipped,
            "per_act": details}


def change_profile(path: Path, law_ids: list[str]) -> dict:
    """What changes between consecutive versions of an article (same pairs as bench.py: non-deleted, non-zero-length
    versions, newer one starting 1990 or later). Amount change = bench.amounts() key present in both with a different
    value (the amount-probe criterion); percentage change = a 百分之N that differs; full-text = the newer version comes
    from a 全文修正 (whole-act revision, articles often renumbered)."""
    import bench  # original (amounts)
    con = ro(path)
    con.row_factory = sqlite3.Row
    ph = ",".join("?" * len(law_ids))
    full = {(r[0], r[1]) for r in con.execute(f"SELECT law_id, ly_version FROM version WHERE law_id IN ({ph}) AND "
                                               "action LIKE '%全文%'", law_ids)}
    n = n_amt = n_pct = n_full = 0
    pct_rx = re.compile(r"百分之[〇零一二三四五六七八九十點\d.]+")
    keys = con.execute(f"SELECT law_id, article_no FROM article_version WHERE law_id IN ({ph}) AND deleted=0 "
                       "GROUP BY 1,2 HAVING count(*)>=2", law_ids).fetchall()
    for k in keys:
        vs = con.execute("SELECT * FROM article_version WHERE law_id=? AND article_no=? AND deleted=0 "
                         "AND (valid_to IS NULL OR valid_to>valid_from) ORDER BY valid_from", (k[0], k[1])).fetchall()
        for prev, cur in zip(vs, vs[1:]):
            if cur["valid_from"] < "1990-01-01":
                continue
            n += 1
            pa = {a: v for a, v, _ in bench.amounts(prev["text"])}
            ca = {a: v for a, v, _ in bench.amounts(cur["text"])}
            n_amt += any(a in pa and pa[a] != v and len(a) >= 6 for a, v in ca.items())
            n_pct += sorted(pct_rx.findall(prev["text"])) != sorted(pct_rx.findall(cur["text"]))
            n_full += (cur["law_id"], cur["first_ly_version"]) in full
    vcount = con.execute(f"SELECT count(*), sum(action LIKE '%全文%') FROM version WHERE law_id IN ({ph})", law_ids).fetchone()
    return {"article_transitions_since_1990": n, "with_amount_change": n_amt,
            "share_amount_change": round(n_amt / n, 3) if n else None, "with_percentage_change": n_pct,
            "from_full_text_revision": n_full, "share_from_full_text_revision": round(n_full / n, 3) if n else None,
            "versions": vcount[0], "full_text_revisions": vcount[1]}


def acts_table(path: Path) -> list[dict]:
    """One row per act of the ChronoMed store (for the data table of the report)."""
    con = ro(path)
    out = []
    for lid, name, name_en, pcode in con.execute("SELECT law_id, name, name_en, pcode FROM law").fetchall():
        v = con.execute("SELECT count(*), min(ly_date), max(ly_date), sum(effective > date(promulgated, '+2 days')) "
                        "FROM version WHERE law_id=?", (lid,)).fetchone()
        av = con.execute("SELECT count(*) FROM article_version WHERE law_id=? AND deleted=0", (lid,)).fetchone()[0]
        out.append({"law_id": lid, "name": name, "name_en": name_en, "pcode": pcode, "versions": v[0],
                    "first_ly_date": v[1], "last_ly_date": v[2], "delayed_versions": v[3], "article_versions": av})
    return out


def main() -> None:
    med_ids = list(registry_med.laws())
    tax_ids = list(registry.LAWS)
    tax_codes = json.loads((TAX_RAW / "moj" / "pcodes.json").read_text(encoding="utf-8"))
    med_codes = registry_med.pcodes()
    med_pages = {lid: moj_med.page(med_codes[lid]) for lid in med_ids}
    tax_pages = {lid: (TAX_RAW / "moj" / f"{tax_codes[lid]}-history.html").read_text(encoding="utf-8", errors="ignore")
                 for lid in tax_ids}
    med_meta = {lid: json.loads((medcfg.RAW_LY / lid / "_law.json").read_text(encoding="utf-8")) for lid in med_ids}
    tax_meta = {lid: json.loads((TAX_RAW / "ly" / lid / "_law.json").read_text(encoding="utf-8")) for lid in tax_ids}
    res = {
        "stores": {"medical_chronomed": store_stats(DB, med_ids),
                   "medical_tax_parser": store_stats(TAXPARSER_DB, med_ids),
                   "tax_chronotax": store_stats(TAX_DB, tax_ids)},
        "history_forms": {"medical": history_stats(med_pages, med_meta), "tax": history_stats(tax_pages, tax_meta)},
        "commencement_articles": {"medical": commencement_article_stats(medcfg.RAW_LY, med_ids),
                                  "tax": commencement_article_stats(TAX_RAW / "ly", tax_ids)},
        "change_profile": {"medical": change_profile(DB, med_ids), "tax": change_profile(TAX_DB, tax_ids)},
        "acts_table": acts_table(DB),
    }
    # how many article versions start on a different date in the two medical stores (same LY texts)
    a = {(r[0], r[1], r[2]): r[3] for r in ro(DB).execute(
        "SELECT law_id, article_no, text, valid_from FROM article_version WHERE deleted=0")}
    b = {(r[0], r[1], r[2]): r[3] for r in ro(TAXPARSER_DB).execute(
        "SELECT law_id, article_no, text, valid_from FROM article_version WHERE deleted=0")}
    common = set(a) & set(b)
    res["medical_store_comparison"] = {
        "article_versions_in_both": len(common),
        "start_date_differs": sum(a[k] != b[k] for k in common),
        "only_in_chronomed": len(set(a) - set(b)), "only_in_tax_parser": len(set(b) - set(a))}
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_atomic(RESULTS / "store_stats.json", json.dumps(res, ensure_ascii=False, indent=1))
    keys = ["acts", "versions", "articles", "article_versions", "versions_delayed_commencement", "versions_retroactive",
            "version_delay_days_median", "versions_delay_ge_180d", "article_versions_retroactive",
            "article_versions_delayed", "article_versions_overtaken", "versions_unmatched_ly_date_fallback",
            "versions_unknown_date_using_promulgation", "versions_pending_no_date", "article_versions_with_per_article_date"]
    print(f"{'':45s} {'med (ChronoMed)':>16s} {'med (tax rules)':>16s} {'tax (ChronoTax)':>16s}")
    for k in keys:
        print(f"{k:45s} " + " ".join(f"{str(res['stores'][s][k]):>16s}" for s in res["stores"]))
    for dom in ("medical", "tax"):
        h = res["history_forms"][dom]
        print(dom, {k: v for k, v in h.items() if k not in ("differences", "unparsed_clauses", "delayed_entries")},
              "unparsed:", h["unparsed_clauses"])
        print("   commencement articles:", {k: v for k, v in res["commencement_articles"][dom].items() if k != "per_act"})
    print(res["medical_store_comparison"])
    print("change profile:", res["change_profile"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
