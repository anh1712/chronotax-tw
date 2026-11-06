"""Freeze the published probe sets and re-derive their gold labels from the corrected store (date fix 2026-10-26).

  python -I -B src/audit/relabel_bench.py   -> data/bench/{tw_taxtime_v0,rerank_test,tw_taxtime_nl}.jsonl (relabelled)
                                               data/audit/out/relabel_log.json

Inputs: the pre-fix files in data/bench/_prefix_2026-10-26/ (never re-sampled: same probes, same dates, same queries)
and the corrected data/lawtw.db. The derivation is first checked on the pre-fix store (data/backup_before_datefix/
lawtw.db, read-only): it must reproduce every original gold label.
  version_id / amount / span   gold = the article version in force on the probe date
  bitemporal                   gold = the version for valid_on as known on known_on (published <= known_on)
  amount, gold changed         gold_amount = amount for the probe's context key in the new gold text;
                               temporal_distractor = the old gold amount (the version the query was cut from)
  span, gold changed           temporal_distractor_id = the old gold version
  rerank_test                  candidate ids unchanged (static top-30 ignores dates; checked by re-running the
                               query); candidate intervals and passages rebuilt with rerank.passage
  tw_taxtime_nl                gold_version_id / gold_amount / temporal_distractor as for amount probes
Every relabelled probe gets "relabel_2026_10_26": {old values}. rerank_train.jsonl (the models' training data) and
summary.json are not changed.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BENCH, ROOT, OUT, write_json  # noqa: E402

import rerank  # noqa: E402  original passage() / fts()
from bench import amounts  # noqa: E402  original

PRE = BENCH / "_prefix_2026-10-26"
NEW_DB = ROOT / "data" / "lawtw.db"
OLD_DB = ROOT / "data" / "backup_before_datefix" / "lawtw.db"
IN_FORCE = "valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"


def ro(p):
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def in_force(con, law_id, art, d):
    r = con.execute(f"SELECT id, deleted FROM article_version WHERE law_id=? AND article_no=? AND {IN_FORCE} "
                    "ORDER BY valid_from DESC, id DESC", (law_id, art, d, d)).fetchall()
    return (None if r[0]["deleted"] else r[0]["id"]) if r else None


def known(con, law_id, art, valid_on, known_on):
    cols = [x[1] for x in con.execute("PRAGMA table_info(article_version)")]
    pend = " AND pending=0" if "pending" in cols else ""
    r = con.execute("SELECT id FROM article_version WHERE law_id=? AND article_no=? AND published<=? AND valid_from<=? "
                    f"AND deleted=0{pend} ORDER BY valid_from DESC, published DESC LIMIT 1",
                    (law_id, art, known_on, valid_on)).fetchone()
    return r["id"] if r else None


def gold(con, p):
    if p["type"] == "bitemporal":
        return known(con, p["law_id"], p["article"], p["valid_on"], p["known_on"])
    return in_force(con, p["law_id"], p["article"], p["as_of"])


def amount_in(con, vid, key):
    t = con.execute("SELECT text FROM article_version WHERE id=?", (vid,)).fetchone()["text"]
    return {k: v for k, v, _ in amounts(t)}.get(key)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    old, new = ro(OLD_DB), ro(NEW_DB)
    probes = [json.loads(l) for l in (PRE / "tw_taxtime_v0.jsonl").open(encoding="utf-8")]
    # 1. the derivation reproduces every original label on the pre-fix store
    bad = [p["id"] for p in probes if gold(old, p) != p["gold_version_id"]]
    assert not bad, f"derivation does not reproduce {len(bad)} original labels: {bad[:5]}"
    log = {"checked_on_prefix_store": len(probes), "tw_taxtime_v0": [], "rerank_test": [], "tw_taxtime_nl": []}
    # 2. relabel TW-TaxTime v0
    out = []
    for p in probes:
        g = gold(new, p)
        if g != p["gold_version_id"]:
            rec = {"old_gold_version_id": p["gold_version_id"]}
            q = {**p, "gold_version_id": g}
            if p["type"] == "amount":
                rec.update(old_gold_amount=p["gold_amount"], old_temporal_distractor=p["temporal_distractor"])
                q["gold_amount"] = amount_in(new, g, p["context_key"]) if g else None
                q["temporal_distractor"] = p["gold_amount"]
            elif p["type"] == "span":
                rec["old_temporal_distractor_id"] = p["temporal_distractor_id"]
                q["temporal_distractor_id"] = p["gold_version_id"]
            elif p["type"] == "version_id":
                rec["old_gold_from"] = p["gold_from"]
                q["gold_from"] = new.execute("SELECT valid_from FROM article_version WHERE id=?", (g,)).fetchone()[0] if g else None
            q["relabel_2026_10_26"] = rec
            log["tw_taxtime_v0"].append({"id": p["id"], "type": p["type"], **rec, "new_gold_version_id": g,
                                         **({"new_gold_amount": q["gold_amount"]} if p["type"] == "amount" else {})})
            p = q
        out.append(p)
    with (BENCH / "tw_taxtime_v0.jsonl").open("w", encoding="utf-8") as f:
        for p in out:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    byid = {p["id"]: p for p in out}
    # 3. rerank test set: same candidates, intervals/passages/gold from the corrected store
    rows = [json.loads(l) for l in (PRE / "rerank_test.jsonl").open(encoding="utf-8")]
    cand_mismatch = 0
    with (BENCH / "rerank_test.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            p = byid[r["id"]]
            ids_now = [x["id"] for x in rerank.fts(new, p["law_id"], p["context"], 30)]
            cand_mismatch += ids_now != [c["id"] for c in r["cands"]]
            cands = []
            for c in r["cands"]:
                v = new.execute("SELECT * FROM article_version WHERE id=?", (c["id"],)).fetchone()
                cands.append({**c, "valid_from": v["valid_from"], "valid_to": v["valid_to"], "p": rerank.passage(v, p["context"])})
            g = p["gold_version_id"]
            if g != r["gold"]:
                log["rerank_test"].append({"id": r["id"], "old_gold": r["gold"], "new_gold": g})
            f.write(json.dumps({**r, "gold": g, "cands": cands}, ensure_ascii=False) + "\n")
    log["rerank_candidate_lists_differing_from_stored"] = cand_mismatch
    # 4. NL questions (gold is the amount probe's gold)
    nl = [json.loads(l) for l in (PRE / "tw_taxtime_nl.jsonl").open(encoding="utf-8")]
    with (BENCH / "tw_taxtime_nl.jsonl").open("w", encoding="utf-8") as f:
        for q in nl:
            p = byid.get(q.get("probe_id"))
            if p and "gold_version_id" in q and p["gold_version_id"] != q["gold_version_id"]:
                rec = {k: q[k] for k in ("gold_version_id", "gold_amount", "temporal_distractor")}
                q = {**q, "gold_version_id": p["gold_version_id"], "gold_amount": p["gold_amount"],
                     "temporal_distractor": p["temporal_distractor"], "relabel_2026_10_26": rec}
                log["tw_taxtime_nl"].append({"probe_id": q["probe_id"], "old": rec,
                                             "new": {k: q[k] for k in rec}, "rejected": q.get("rejected")})
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    log["counts"] = {k: len(v) for k, v in log.items() if isinstance(v, list)}
    log["counts_by_type"] = {t: sum(x["type"] == t for x in log["tw_taxtime_v0"]) for t in ("version_id", "amount", "span", "bitemporal")}
    log["gold_none"] = [x["id"] for x in log["tw_taxtime_v0"] if x["new_gold_version_id"] is None]
    write_json(OUT / "relabel_log.json", log)
    print(json.dumps({k: v for k, v in log.items() if k in ("checked_on_prefix_store", "counts", "counts_by_type",
                                                             "rerank_candidate_lists_differing_from_stored", "gold_none")},
                     ensure_ascii=False))
    for x in log["tw_taxtime_v0"]:
        print("  ", x)


if __name__ == "__main__":
    main()
