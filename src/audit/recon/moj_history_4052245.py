"""Parse the MOJ amendment history page (法規沿革) into promulgation + effective dates.

Each entry reads like:
  71. 中華民國一百十五年九月十一日總統華總一經字第…號令修正公布第 17、126 條條文；並自一百十五年一月一日施行
  69. …令修正公布第 88、…、126 條條文；依第 126 條規定：施行日期，由行政院定之 … 令發布定自一百十四年一月一日施行
Effective date rule (中央法規標準法 §13): unless the text names a date, a law takes effect from the third day
counting the promulgation day, i.e. promulgation + 2 days. We record which rule produced each date.
"""
import datetime as dt
import html
import re
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "moj"
UA = {"User-Agent": "LAW-TW research prototype"}

_DIG = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_num(s: str) -> int:
    """Chinese numerals up to 999 (一百十五, 三十九, 十二, 一百零五)."""
    if s.isdigit():
        return int(s)
    total, cur = 0, 0
    for ch in s:
        if ch in _DIG:
            cur = _DIG[ch]
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
        elif ch == "百":
            total += (cur or 1) * 100
            cur = 0
    return total + cur


_ROC_DATE = r"(?:中華民國)?([〇零一二三四五六七八九十百\d]+)年([〇零一二三四五六七八九十\d]+)月([〇零一二三四五六七八九十\d]+)日"


def roc_date(m: re.Match) -> dt.date:
    return dt.date(cn_num(m.group(1)) + 1911, cn_num(m.group(2)), cn_num(m.group(3)))


def fetch(pcode: str) -> str:
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / f"{pcode}-history.html"
    if not f.exists():
        url = f"https://law.moj.gov.tw/LawClass/LawHistory.aspx?pcode={pcode}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            f.write_bytes(r.read())
    return f.read_text(encoding="utf-8", errors="ignore")


def parse(page: str) -> list[dict]:
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    chunks = re.split(r"\n\s*(?=\d+\s*\.\s*中華民國)", text)[1:]
    out = []
    for c in chunks:
        c = " ".join(c.split())
        c = c.split("本網站法規資料")[0].strip()
        no = int(re.match(r"(\d+)", c).group(1))
        m = re.search(_ROC_DATE, c)
        promulgated = roc_date(m)
        eff, basis = None, "default_§13"
        # explicit effective date: "自…施行" / "定自…施行" (take the LAST one: the Executive Yuan order wins)
        for em in re.finditer(r"自" + _ROC_DATE + r"(?:起)?施行", c):
            eff, basis = roc_date(em), "explicit"
        if eff is None and re.search(r"施行日期，?由行政院定之", c):
            basis = "by_executive_yuan_unknown"  # date set later by an order not in this entry
        if eff is None and basis == "default_§13":
            eff = promulgated + dt.timedelta(days=2)
        arts = re.search(r"公布第\s*([\d\s、～\-－之]+?)\s*條", c)
        out.append({
            "no": no,
            "promulgated": promulgated.isoformat(),
            "effective": eff.isoformat() if eff else None,
            "effective_basis": basis,
            "whole_text": "全文" in c[:80],
            "articles": [a.strip() for a in re.split(r"[、\s]+", arts.group(1)) if a.strip()] if arts else [],
            "note": c,
        })
    return sorted(out, key=lambda e: e["promulgated"])
