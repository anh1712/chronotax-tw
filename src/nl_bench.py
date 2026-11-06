"""TW-TaxTime-NL: natural-language questions with RULE-based gold, and an end-to-end evaluation.

Generation: an LLM sees one amount probe (law, article, the version text that applies on the date, the date) and writes
the question a taxpayer would ask — paraphrased, with the date in natural form. The gold is NOT written by the LLM:
it stays the probe's article-version id and amount. Questions that copy ≥ 8 consecutive characters of the law text,
or that omit the year, are rejected (no lexical leakage, no unanswerable period).

Evaluation (end to end, through answer.ask): period resolved from the question text, retrieval of the gold version
(R@1 / R@5), and the answer: correct amount stated, temporal distractor (the neighbouring version's amount) stated,
verified by code. Infrastructure errors (gateway) are reported separately and excluded.

  python -I src/nl_bench.py gen 150      # → data/bench/tw_taxtime_nl.jsonl (resumable)
  python -I src/nl_bench.py eval         # → data/bench/results_nl.json
"""
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer  # noqa: E402
from bench import cn_amount  # noqa: E402
from eval_retrieval import wilson  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "data" / "bench"
OUT = BENCH / "tw_taxtime_nl.jsonl"

GEN = """You write realistic questions that a taxpayer or accountant in Taiwan would ask.
Below is a provision of {law} {article}, in force on {as_of}. The fact to ask about is the amount right after this
context: 「{context}」, which is {amount:,} 元 in this version.
Write ONE question in Traditional Chinese (Taiwan usage) that asks for that amount for the period around {as_of}.
Rules: express the date naturally (民國 year, e.g. 民國{roc}年, or a full date); do NOT copy 8 or more consecutive
characters from the provision; do not mention the answer; do not mention article numbers.
Return JSON: {{"question": "..."}}
Provision text:
{text}"""


def _roc(d: str) -> int:
    return int(d[:4]) - 1911


def _leaks(q: str, text: str, n: int = 8) -> bool:
    t = re.sub(r"\s", "", text)
    q = re.sub(r"\s", "", q)
    return any(q[i:i + n] in t for i in range(len(q) - n + 1))


def gen(n: int, seed: int = 23) -> None:
    import sqlite3
    probes = [json.loads(l) for l in (BENCH / "tw_taxtime_v0.jsonl").open(encoding="utf-8")]
    probes = [p for p in probes if p["type"] == "amount" and p["as_of"] >= "2000-01-01"]
    random.Random(seed).shuffle(probes)
    done = {json.loads(l)["probe_id"] for l in OUT.open(encoding="utf-8")} if OUT.exists() else set()
    con = sqlite3.connect(answer.DB)
    todo = [p for p in probes if p["id"] not in done][: max(0, n - len(done))]

    def one(p):
        text = con.execute("SELECT text FROM article_version WHERE id=?", (p["gold_version_id"],)).fetchone()[0]
        prompt = GEN.format(law=p["law"], article=p["article"], as_of=p["as_of"], context=p["context"],
                            amount=p["gold_amount"], roc=_roc(p["as_of"]), text=text[:2500])
        try:
            r = answer.llm(prompt) or {}
        except Exception as e:
            return {"probe_id": p["id"], "error": str(e)}
        q = (r.get("question") or "").strip()
        bad = ("no_question" if not q else "leak" if _leaks(q, text) else
               "no_year" if not re.search(r"\d{2,4}|[一二三四五六七八九十百]+年", q) else None)
        return {"probe_id": p["id"], "question": q, "rejected": bad, **{k: p[k] for k in (
            "law_id", "law", "article", "as_of", "gold_version_id", "gold_amount", "temporal_distractor")}}

    con.close()
    con = None
    import sqlite3 as _s
    con = _s.connect(answer.DB, check_same_thread=False)
    with ThreadPoolExecutor(2) as ex, OUT.open("a", encoding="utf-8") as f:
        for row in ex.map(one, todo):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
    rows = [json.loads(l) for l in OUT.open(encoding="utf-8")]
    print(f"{len(rows)} generated; ok {sum(1 for r in rows if r.get('question') and not r.get('rejected'))}, "
          f"rejected {sum(1 for r in rows if r.get('rejected'))}, errors {sum(1 for r in rows if 'error' in r)}")


def _amounts(text: str) -> set[int]:
    out = set()
    for m in re.finditer(r"([〇零一二兩三四五六七八九十百千萬億\d,]+)\s*(萬元|元)", text):
        v = cn_amount(m.group(1) + ("萬" if m.group(2) == "萬元" else ""))
        if v:
            out.add(v)
    for m in re.finditer(r"(?:NT\$|NTD\s?)?([\d,]{4,})", text):
        out.add(int(m.group(1).replace(",", "")))
    return out


def evaluate() -> None:
    rows = [json.loads(l) for l in OUT.open(encoding="utf-8")]
    rows = [r for r in rows if r.get("question") and not r.get("rejected")]

    def one(r):
        try:
            res = answer.ask(r["question"], None)
        except Exception as e:
            return {"id": r["probe_id"], "infra": str(e)}
        if res.get("mode") == "llm_error":
            return {"id": r["probe_id"], "infra": res.get("error")}
        ids = [s["id"] for s in res["sources"]]
        stated = set().union(*[_amounts(c["text"]) for c in res.get("claims", [])]) if res.get("claims") else set()
        return {"id": r["probe_id"], "period": res["period"], "year_ok": res["period"]["as_of"][:4] == r["as_of"][:4]
                or abs(int(res["period"]["as_of"][:4]) - int(r["as_of"][:4])) <= 1,
                "r1": bool(ids) and ids[0] == r["gold_version_id"], "r5": r["gold_version_id"] in ids,
                "amount_ok": r["gold_amount"] in stated, "distractor": r["temporal_distractor"] in stated
                and r["temporal_distractor"] != r["gold_amount"],
                "all_verified": bool(res.get("claims")) and all(c["verified"] for c in res["claims"]),
                "insufficient": res.get("insufficient", False)}

    with ThreadPoolExecutor(2) as ex:
        out = list(ex.map(one, rows))
    ok = [o for o in out if "infra" not in o]
    n = len(ok)
    summ = {"questions": len(rows), "evaluated": n, "infra_errors": len(out) - n}
    for k in ("year_ok", "r1", "r5", "amount_ok", "distractor", "all_verified", "insufficient"):
        c = sum(bool(o.get(k)) for o in ok)
        summ[k] = {"rate": round(c / n, 3) if n else None, "ci": wilson(c, n)}
    # does code verification catch wrong answers? among answers without the gold amount, share flagged unverified
    wrong = [o for o in ok if not o["amount_ok"] and not o["insufficient"]]
    summ["wrong_answers_flagged_by_code"] = {"n": len(wrong), "flagged": sum(not o["all_verified"] for o in wrong)}
    (BENCH / "results_nl.json").write_text(json.dumps({"summary": summ, "items": out}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "gen":
        gen(int(sys.argv[2]) if len(sys.argv) > 2 else 150)
    else:
        evaluate()
