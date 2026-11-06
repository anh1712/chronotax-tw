"""Extension probes (NOT in the ChronoTax generator): questions asked between promulgation and commencement.

  python -I src/med/window_med.py   -> data/med/results/window_probes.json

Health acts often start months or years after promulgation (病人自主權利法: promulgated 2016-01-06, in force
2019-01-06). In that window the newest PUBLISHED text is not yet the text IN FORCE. For every article version whose
start is later than the 中央法規標準法 §13 default (promulgation + 2 days) and on/after 1990-01-01, one date is drawn
uniformly inside (promulgation + 2 days, start) (seed 19). Gold = the text in force on that date in the store
(the previous text, or "not in force yet"). Systems, compared by text:
  publication-keyed  the newest text promulgated on or before the date (knows publication, ignores commencement)
  validity (store)   the text whose [valid_from, valid_to) contains the date (correct by construction; sanity check)
  tax-rule store     medical only: the same lookup in medtw_taxparser.db (the unchanged tax-law date rules)
Tax windows come from data/lawtw.db (READ-ONLY), so both domains are measured the same way.
"""
import datetime as dt
import json
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402
from medcfg import DB, MED, RESULTS, TAX_DB, write_atomic  # noqa: E402
import eval_retrieval  # noqa: E402  original (wilson)
import registry  # noqa: E402  original (tax act list)
import registry_med  # noqa: E402

TAXPARSER_DB = MED / "medtw_taxparser.db"
IN_FORCE = "deleted=0 AND valid_from<=:d AND (valid_to IS NULL OR valid_to>:d)"


def ro(p: Path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def text_in_force(con, law, art, d):
    r = con.execute(f"SELECT text FROM article_version WHERE law_id=:l AND article_no=:a AND {IN_FORCE}",
                    {"l": law, "a": art, "d": d}).fetchone()
    return r["text"] if r else None


def text_published(con, law, art, d):
    r = con.execute("SELECT text, deleted FROM article_version WHERE law_id=? AND article_no=? AND published<=? "
                    "ORDER BY published DESC, valid_from DESC, id DESC LIMIT 1", (law, art, d)).fetchone()
    return None if (r is None or r["deleted"]) else r["text"]


def probes(con, law_ids, rng) -> list[dict]:
    ph = ",".join("?" * len(law_ids))
    rows = con.execute(f"SELECT * FROM article_version WHERE law_id IN ({ph}) AND deleted=0 AND overtaken=0 "
                       "AND published IS NOT NULL AND valid_from>=? AND (valid_to IS NULL OR valid_to>valid_from) "
                       "ORDER BY law_id, article_no, valid_from", (*law_ids, "1990-01-01")).fetchall()
    out = []
    for v in rows:
        lo = dt.date.fromisoformat(v["published"]) + dt.timedelta(days=2)
        hi = dt.date.fromisoformat(v["valid_from"])
        if (hi - lo).days < 2:
            continue
        d = (lo + dt.timedelta(days=rng.randrange(1, (hi - lo).days))).isoformat()
        out.append({"law_id": v["law_id"], "article": v["article_no"], "date": d, "new_version_id": v["id"],
                    "promulgated": v["published"], "starts": v["valid_from"], "window_days": (hi - lo).days + 2,
                    "gold_text": text_in_force(con, v["law_id"], v["article_no"], d)})
    return out


def rate(k, n):
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "ci": eval_retrieval.wilson(k, n)}


def main() -> None:
    rng = random.Random(19)
    med, tax, tp = ro(DB), ro(TAX_DB), ro(TAXPARSER_DB)
    res = {}
    for dom, con, ids in (("medical", med, list(registry_med.laws())), ("tax", tax, list(registry.LAWS))):
        ps = probes(con, ids, rng)
        wrong_pub = sum(text_published(con, p["law_id"], p["article"], p["date"]) != p["gold_text"] for p in ps)
        ok_store = sum(text_in_force(con, p["law_id"], p["article"], p["date"]) == p["gold_text"] for p in ps)
        days = sorted(p["window_days"] for p in ps)
        res[dom] = {"probes": len(ps), "acts_with_windows": len({p["law_id"] for p in ps}),
                    "not_in_force_yet_gold": sum(p["gold_text"] is None for p in ps),
                    "window_days_median": days[len(days) // 2] if days else None,
                    "window_days_max": days[-1] if days else None,
                    "publication_keyed_wrong": rate(wrong_pub, len(ps)),
                    "validity_store_correct": rate(ok_store, len(ps))}
        if dom == "medical":
            wrong_tp = [p for p in ps if text_in_force(tp, p["law_id"], p["article"], p["date"]) != p["gold_text"]]
            by = {}
            for p in wrong_tp:
                by[p["law_id"]] = by.get(p["law_id"], 0) + 1
            res[dom]["tax_rule_store_wrong"] = rate(len(wrong_tp), len(ps))
            res[dom]["tax_rule_store_wrong_by_act"] = {registry_med.laws()[k][0]: v for k, v in by.items()}
        per_act = {}
        for p in ps:
            per_act[p["law_id"]] = per_act.get(p["law_id"], 0) + 1
        res[dom]["probes_by_act"] = per_act
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_atomic(RESULTS / "window_probes.json", json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
