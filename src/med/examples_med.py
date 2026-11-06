"""Three "same question, different correct answer depending on the date" examples from health law.

  python -I src/med/examples_med.py   -> data/med/results/examples.json

Each answer is checkable by rule: the article version in force on the date (data/med/medtw.db, dates hand-checked in
handcheck_med.py) and one number in it (an amount or an age). Official English = MOJ English text, which exists only
for the CURRENT version; glosses of older versions are ours and are labelled so. For each date we also show what the
three indexes of eval_retrieval return for a cloze query taken from the law text (top 1, same SQL as the benchmark).
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402
from medcfg import DB, RESULTS, write_atomic  # noqa: E402
import bench  # noqa: E402  original (cn_amount)
import eval_retrieval  # noqa: E402  original (MODES)

EXAMPLES = [
    {"id": "nhi_supplementary_premium", "law_id": "01189", "pcode": "L0060001",
     "question": "A hospital pays a visiting doctor (insured through another employer) a salary. Must it withhold an "
                 "NHI supplementary premium (補充保險費)?",
     "dates": ["2012-06-01", "2013-06-01"], "query": '"非所屬投保單位給付之薪資所得"', "en_article": "第三十一條",
     "answer_rx": r"非所屬投保單位給付之薪資所得",
     "why": "二代健保 text promulgated 2011-01-26 but in force only from 2013-01-01 (Art. 31 para. 1 item 2). In 2012 the "
            "newest PUBLISHED text already had the rule, but it did not apply yet."},
    {"id": "pharma_fine_cap", "law_id": "02510", "pcode": "L0030001",
     "question": "What is the maximum fine under Pharmaceutical Affairs Act Art. 92 para. 1 (e.g. for breaking Art. 57 "
                 "manufacturing rules)?",
     "dates": ["2014-06-01", "2016-06-01"], "query": '"規定之一者，處新臺幣三萬元以上"', "en_article": "第九十二條",
     "answer_rx": r"規定之一者，處新臺幣三萬元以上([〇零一二兩三四五六七八九十百千萬億\d,]+)元以下罰鍰",
     "why": "Amendment promulgated 2015-12-02 (in force 2015-12-04) raised the cap from NT$150,000 to NT$2,000,000."},
    {"id": "smoking_age", "law_id": "02549", "pcode": "L0070021",
     "question": "May a 19-year-old smoke in Taiwan?",
     "dates": ["2022-06-01", "2024-06-01"], "query": '"實際為照顧之人" "不得吸菸"', "en_article": "第十六條",
     "answer_rx": r"未滿([一二三四五六七八九十]+)歲(?:者|之人)(?:及孕婦)?，不得吸菸",
     "why": "2023 full revision (in force 2023-03-22) raised the age from 18 to 20 and moved the rule from Art. 12 to "
            "Art. 16."},
]
IN_FORCE = "deleted=0 AND valid_from<=:d AND (valid_to IS NULL OR valid_to>:d)"


def top1(con, law, q, d, mode):
    """Same query as eval_retrieval.run (FTS5 trigram, bm25, law filter, mode filter), top 1 row; q is an FTS5
    expression of quoted phrases (all must occur)."""
    r = con.execute(
        f"SELECT av.id, av.article_no, av.valid_from, av.valid_to, av.text FROM article_fts f JOIN article_version av "
        f"ON av.id=f.rowid WHERE article_fts MATCH :q AND av.law_id=:l AND av.deleted=0 {eval_retrieval.MODES[mode]} "
        f"ORDER BY bm25(article_fts), av.valid_from DESC LIMIT 1", {"q": q, "l": law, "d": d}).fetchone()
    return r


def value(rx, text):
    m = re.search(rx, text or "")
    if not m:
        return None
    if not m.groups():
        return True
    g = m.group(1)
    return bench.cn_amount(g) if "歲" not in rx else {"十八": 18, "二十": 20}.get(g, g)


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = []
    for ex in EXAMPLES:
        e = dict(ex)
        en = con.execute("SELECT label, text, en_amended FROM article_en WHERE law_id=? AND article_no=?",
                         (ex["law_id"], ex["en_article"])).fetchone()
        e["official_english_current"] = dict(en) if en else None
        e["by_date"] = {}
        for d in ex["dates"]:
            gold = [dict(r) for r in con.execute(
                f"SELECT id, article_no, valid_from, valid_to, from_basis, published, text FROM article_version "
                f"WHERE law_id=:l AND {IN_FORCE}", {"l": ex["law_id"], "d": d}) if re.search(ex["answer_rx"], r["text"])]
            row = {"in_force_articles_matching": [
                {"article": g["article_no"], "valid_from": g["valid_from"], "valid_to": g["valid_to"],
                 "basis": g["from_basis"], "promulgated": g["published"], "value": value(ex["answer_rx"], g["text"]),
                 "snippet": re.search(r"[^。；]*" + ex["answer_rx"] + r"[^。；]*", g["text"]).group(0)[:120]}
                for g in gold]}
            row["answer"] = row["in_force_articles_matching"][0]["value"] if gold else "no such rule in force"
            row["indexes"] = {}
            for mode in eval_retrieval.MODES:
                r = top1(con, ex["law_id"], ex["query"], d, mode)
                row["indexes"][mode] = None if r is None else {
                    "article": r["article_no"], "valid_from": r["valid_from"], "valid_to": r["valid_to"],
                    "in_force_on_date": r["valid_from"] <= d and (r["valid_to"] is None or r["valid_to"] > d),
                    "value": value(ex["answer_rx"], r["text"])}
            e["by_date"][d] = row
        out.append(e)
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_atomic(RESULTS / "examples.json", json.dumps(out, ensure_ascii=False, indent=1))
    for e in out:
        print("==", e["id"], "|", e["question"])
        for d, row in e["by_date"].items():
            print("  ", d, "answer:", row["answer"], "|", [(g["article"], g["valid_from"], g["snippet"][:50]) for g in
                                                           row["in_force_articles_matching"]])
            for m, r in row["indexes"].items():
                print("      ", m, r)
        print("   EN:", (e["official_english_current"] or {}).get("text", "")[:240].replace("\n", " "))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
