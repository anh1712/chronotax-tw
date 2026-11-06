"""Retrieval on TW-TaxTime `amount` probes: does the retriever return the article VERSION that applies on the date?

Query = the cloze context of the changed amount (e.g. 「稅義務人欠繳稅捐金額達新臺幣」), restricted to the law.
  static      — FTS over every stored version, date ignored (what a plain RAG index over law texts does)
  latest      — FTS over current texts only (what an index of today's law does)
  temporal    — FTS over versions in force on the probe date (this system)
Metrics: R@1 / R@5 of the gold version; misgrounding@1 = top hit is the right ARTICLE but the wrong VERSION.
Wilson 95% intervals. Output: data/bench/results_retrieval.json
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "lawtw.db"
BENCH = ROOT / "data" / "bench" / "tw_taxtime_v0.jsonl"

MODES = {
    "static": "",
    "latest": "AND av.valid_to IS NULL",
    "temporal": "AND av.valid_from <= :d AND (av.valid_to IS NULL OR av.valid_to > :d)",
}


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - r) / d, 3), round((c + r) / d, 3))


def run(con, items, mode: str, k: int = 5) -> dict:
    hit1 = hit5 = mis1 = 0
    for it in items:
        q = '"' + it["context"].replace('"', "") + '"'
        rows = con.execute(
            f"SELECT av.id, av.article_no FROM article_fts f JOIN article_version av ON av.id=f.rowid "
            f"WHERE article_fts MATCH :q AND av.law_id=:l AND av.deleted=0 {MODES[mode]} "
            f"ORDER BY bm25(article_fts), av.valid_from DESC LIMIT :k",
            {"q": q, "l": it["law_id"], "d": it["as_of"], "k": k}).fetchall()
        ids = [r[0] for r in rows]
        hit1 += bool(ids) and ids[0] == it["gold_version_id"]
        hit5 += it["gold_version_id"] in ids
        mis1 += bool(rows) and rows[0][1] == it["article"] and ids[0] != it["gold_version_id"]
    n = len(items)
    return {"n": n, "R@1": round(hit1 / n, 3), "R@1_ci": wilson(hit1, n), "R@5": round(hit5 / n, 3),
            "misgrounding@1": round(mis1 / n, 3), "misgrounding@1_ci": wilson(mis1, n)}


def main() -> None:
    items = [json.loads(l) for l in BENCH.open(encoding="utf-8")]
    items = [i for i in items if i["type"] == "amount"]
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    res = {m: run(con, items, m) for m in MODES}
    (ROOT / "data" / "bench" / "results_retrieval.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for m, r in res.items():
        print(f"{m:9s} n={r['n']}  R@1={r['R@1']} {r['R@1_ci']}  R@5={r['R@5']}  "
              f"misgrounding@1={r['misgrounding@1']} {r['misgrounding@1_ci']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
