"""TW-TaxTime v0: a rule-graded temporal benchmark generated from the versioned store (0 LLM tokens).

Three probe types, each with a gold answer that is checked by rule, not by an LLM judge:
  version_id   — (law, article, date) → which article version applies. Dates are sampled strictly inside an interval.
  amount       — (law, article, date, context) → the money amount stated in the version that applies, where that
                 amount CHANGED across versions; the amount of the neighbouring version is kept as a temporal distractor.
  bitemporal   — retroactive cases: same (law, article, period) gives different gold texts depending on the
                 knowledge date (before vs after publication of the retroactive amendment).
Output: data/bench/tw_taxtime_v0.jsonl (+ summary). Deterministic (fixed seed).
"""
import datetime as dt
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "lawtw.db"
OUT = ROOT / "data" / "bench"

_D = {"〇": 0, "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_U = {"十": 10, "百": 100, "千": 1000}
AMOUNT_RX = re.compile(r"([〇零一二兩三四五六七八九十百千萬億\d,]+)元")


def cn_amount(s: str) -> int | None:
    """二萬四千 → 24000, 十二萬 → 120000, 1,000 → 1000, 三億 → 300000000."""
    s = s.replace(",", "")
    if s.isdigit():
        return int(s)
    total, section, num = 0, 0, 0
    for tok in re.findall(r"\d+(?:\.\d+)?|.", s):  # Arabic digits may be mixed in: 12萬, 2.5萬
        ch = tok
        if tok[0].isdigit():
            num = float(tok) if "." in tok else int(tok)
        elif ch in _D:
            num = _D[ch]
        elif ch in _U:
            section += (num or 1) * _U[ch]
            num = 0
        elif ch == "萬":
            total += (section + num) * 10_000
            section = num = 0
        elif ch == "億":
            total += (section + num) * 100_000_000
            section = num = 0
        else:
            return None
    v = total + section + num
    return int(v) or None


def amounts(text: str) -> list[tuple[str, int, str]]:
    """(context key, amount, raw context): key = the 14 chars before the number with digits stripped, so it survives
    renumbering across versions; raw = the literal preceding text (used as the query, so it occurs in the source)."""
    out = []
    for m in AMOUNT_RX.finditer(text):
        v = cn_amount(m.group(1))
        if v is None:
            continue
        key = re.sub(r"[\d〇零一二兩三四五六七八九十百千萬億,\s　]", "", text[max(0, m.start() - 24):m.start()])[-14:]
        raw = re.split(r"[，。；：、\n]", text[max(0, m.start() - 30):m.start()])[-1][-16:]
        out.append((key, v, raw))
    return out


def rand_date(rng, a: str, b: str | None) -> str | None:
    lo = dt.date.fromisoformat(a)
    hi = dt.date.fromisoformat(b) if b else dt.date(2026, 10, 1)
    if (hi - lo).days < 2:
        return None
    return (lo + dt.timedelta(days=rng.randrange(1, (hi - lo).days))).isoformat()


def main(seed: int = 19) -> None:
    rng = random.Random(seed)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    names = {r["law_id"]: (r["name"], r["name_en"]) for r in con.execute("SELECT * FROM law")}
    items = []
    keys = con.execute("SELECT law_id, article_no, count(*) n FROM article_version WHERE deleted=0 "
                       "GROUP BY 1,2 HAVING n>=2").fetchall()
    for k in keys:
        vs = con.execute("SELECT * FROM article_version WHERE law_id=? AND article_no=? AND deleted=0 "
                         "AND (valid_to IS NULL OR valid_to>valid_from) ORDER BY valid_from", (k[0], k[1])).fetchall()
        law, law_en = names[k[0]]
        # version_id: one probe per interval, from 1990 on (older texts are rarely asked about)
        for v in vs:
            if v["valid_from"] < "1990-01-01":
                continue
            d = rand_date(rng, v["valid_from"], v["valid_to"])
            if d:
                items.append({"type": "version_id", "law_id": k[0], "law": law, "law_en": law_en, "article": k[1],
                              "as_of": d, "gold_version_id": v["id"], "gold_from": v["valid_from"],
                              "n_versions": len(vs)})
        # amount: values that change between consecutive versions under the same context key
        for prev, cur in zip(vs, vs[1:]):
            if cur["valid_from"] < "1990-01-01":
                continue
            pa = {k_: (v_, r_) for k_, v_, r_ in amounts(prev["text"])}
            ca = {k_: (v_, r_) for k_, v_, r_ in amounts(cur["text"])}
            for key, (val, raw_c) in ca.items():
                if key in pa and pa[key][0] != val and len(key) >= 6:
                    for v, other, at, raw in ((cur, pa[key][0], val, raw_c), (prev, val, pa[key][0], pa[key][1])):
                        d = rand_date(rng, v["valid_from"], v["valid_to"])
                        if d:
                            items.append({"type": "amount", "law_id": k[0], "law": law, "law_en": law_en,
                                          "article": k[1], "as_of": d, "context": raw, "context_key": key, "gold_amount": at,
                                          "temporal_distractor": other, "gold_version_id": v["id"]})
    # bitemporal: retroactive versions → ask about a date inside the new interval, before and after publication
    for v in con.execute("SELECT * FROM article_version WHERE retro=1 AND deleted=0").fetchall():
        prior = con.execute("SELECT * FROM article_version WHERE law_id=? AND article_no=? AND published<? "
                            "AND valid_from<=? AND deleted=0 ORDER BY valid_from DESC, published DESC LIMIT 1",
                            (v["law_id"], v["article_no"], v["published"], v["valid_from"])).fetchone()
        if not prior or prior["text"] == v["text"]:
            continue
        law, law_en = names[v["law_id"]]
        base = {"type": "bitemporal", "law_id": v["law_id"], "law": law, "law_en": law_en,
                "article": v["article_no"], "valid_on": v["valid_from"]}
        before = (dt.date.fromisoformat(v["published"]) - dt.timedelta(days=1)).isoformat()
        items.append({**base, "known_on": before, "gold_version_id": prior["id"]})
        items.append({**base, "known_on": v["published"], "gold_version_id": v["id"]})

    OUT.mkdir(parents=True, exist_ok=True)
    for i, it in enumerate(items):
        it["id"] = f"tt-{it['type']}-{i:05d}"
    with (OUT / "tw_taxtime_v0.jsonl").open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    by = {}
    for it in items:
        by[it["type"]] = by.get(it["type"], 0) + 1
    summary = {"seed": seed, "total": len(items), "by_type": by,
               "laws": len({it["law_id"] for it in items}), "articles": len({(it["law_id"], it["article"]) for it in items})}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
