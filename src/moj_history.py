"""Parse the MOJ amendment history page (法規沿革) into promulgation + effective dates.

Each entry reads like:
  71. 中華民國一百十五年九月十一日總統華總一經字第…號令修正公布第 17、126 條條文；並自一百十五年一月一日施行
  69. …令修正公布第 88、…、126 條條文；依第 126 條規定：施行日期，由行政院定之 … 令發布定自一百十四年一月一日施行
Effective date rule (中央法規標準法 §13): unless the text names a date, a law takes effect from the third day
counting the promulgation day, i.e. promulgation + 2 days. We record which rule produced each date.

Commencement clauses are read on WHITESPACE-FREE text (MOJ wraps lines inside words: "自 九十年", "施 行") and each
clause gets a SCOPE (the text since the previous clause or "；。但"):
  - scope names whole articles ("但第4～7條、第12、15條條文，自…施行")   -> per-article rule
  - scope names paragraphs only ("第14條第1項第9類規定，自…施行")        -> partial: recorded, the article keeps the
    main date (an article-level store cannot split an article; the act's commencement article may still date it)
  - scope names no article ("並自…施行", "其餘條文自…施行", an order "定自…施行") -> MAIN date of the amendment
Forms: 自/於/定於 <date> 施行 · 自<Y>年度施行 (tax year -> Jan 1) · 自公布後N年/個月/日施行 · 自公布日施行 (§13) ·
施行期間，自<date>起 (start of an application period) · 施行日期由行政院定之 (delegated: date set by a later order).
Executive Yuan orders printed in the entry ("中華民國…行政院…號令發布…定自…施行") are read the same way.
The LAST date in the entry is no longer applied to the whole amendment: it is often an exception for a few articles.
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


PENDING = "pending"  # delegated to the Executive Yuan and no order in the entry: not in force yet
_N = r"[〇零一二三四五六七八九十百\d]+"
_CLAUSES = [  # (kind, regex) on whitespace-free text; earlier kinds win when two matches overlap
    ("period", re.compile(r"施行期間，?自" + _ROC_DATE + r"起至" + _ROC_DATE + r"止")),
    ("abs", re.compile(r"(?:定)?(?:自|於)" + _ROC_DATE + r"(?:起)?施行")),
    ("tax_year", re.compile(r"(?:定)?自(?:中華民國)?(" + _N + r")年度(?:起)?施行")),
    ("rel", re.compile(r"自(?:公布|發布)(?:日起|後)(" + _N + r")(年|個月|日)(?:起)?施行")),
    ("same_day", re.compile(r"自(?:公布|發布)(?:之)?日(?:起)?施行")),
    ("ey", re.compile(r"(?:其)?(?:施行日期，?)?由行政院(?:以命令)?定之")),
]
# article references in a clause scope (MOJ histories use Arabic numerals): 第5-1條 · 第4～7條 · 第13條至15條 ·
# 第4條第1項第1款 (paragraph level)
_ART = re.compile(r"第(\d+(?:-\d+)?(?:[、～]\d+(?:-\d+)?)*)條(?:至第?(\d+(?:-\d+)?)條)?((?:第\d+[項款類目])*)")
_ORDER = re.compile(r"(?=中華民國" + _N + r"年" + _N + r"月" + _N + r"日行政院)")


def _add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    for day in (d.day, 30, 29, 28):
        try:
            return dt.date(d.year + y, m + 1, day)
        except ValueError:
            continue
    raise ValueError(d)


def _clause_date(kind: str, m: re.Match, prom: dt.date) -> tuple[str, str]:
    if kind == "abs":
        return roc_date(m).isoformat(), "explicit"
    if kind == "period":  # start of an application period ("施行期間，自D1起至D2止"); the end date is not modelled
        return dt.date(cn_num(m.group(1)) + 1911, cn_num(m.group(2)), cn_num(m.group(3))).isoformat(), "explicit_period_start"
    if kind == "tax_year":  # applies from that income year -> Jan 1 (same convention as effect_rules)
        return dt.date(cn_num(m.group(1)) + 1911, 1, 1).isoformat(), "explicit_tax_year"
    if kind == "rel":  # 公布後一年 = same calendar day one year later (MOF: 105-12-28 公布 -> 106-12-28 施行)
        n, unit = cn_num(m.group(1)), m.group(2)
        d = _add_months(prom, 12 * n) if unit == "年" else _add_months(prom, n) if unit == "個月" else prom + dt.timedelta(days=n)
        return d.isoformat(), "relative_after_promulgation"
    if kind == "same_day":  # 自公布日施行 = §13: third day counting the promulgation day
        return (prom + dt.timedelta(days=2)).isoformat(), "default_§13"
    return PENDING, "by_executive_yuan"


def _refs(scope: str) -> tuple[list[str], list[str], bool]:
    """(whole-article refs, paragraph-level refs, paragraph mentioned without an article). Refs keep MOJ notation
    ('5-1', range '4~7'); the caller expands ranges with the act's own article list."""
    scope = re.sub(r"依第[\d\-]+條?規定[：:，]?", "", scope)  # "依第126條規定：" names the commencement article itself
    scope = re.sub(r"除[^，；。]*?外", "", scope)  # "除第16、20條外，其餘…" / "除另有規定外": excluded, not named
    whole, part = [], []
    for m in _ART.finditer(scope):
        toks = m.group(1).split("、")
        if m.group(2):  # 第13條至15條
            toks[-1] = f"{toks[-1]}~{m.group(2)}"
        toks = [t.replace("～", "~") for t in toks]
        (part if m.group(3) else whole).extend(toks)
    para_only = not whole and not part and bool(re.search(r"第\d+[項款類目]", scope))
    return whole, part, para_only


def parse(page: str) -> list[dict]:
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    chunks = re.split(r"\n\s*(?=\d+\s*\.\s*中華民國)", text)[1:]
    out = []
    for c in chunks:
        c = " ".join(c.split())
        c = c.split("本網站法規資料")[0].split(":::")[0].strip()
        no = int(re.match(r"(\d+)", c).group(1))
        promulgated = roc_date(re.search(_ROC_DATE, c))
        t = re.sub(r"\s+", "", c)
        segs = _ORDER.split(t)  # [promulgation, order, order, ...]
        main, main_basis, delegated, rules, partial, clauses = None, None, False, {}, [], []
        for si, seg in enumerate(segs):
            if si:  # an order: keep the text after its number ("…號令發布…", "…號函核定…")
                seg = re.split(r"號(?:令|函)", seg, maxsplit=1)[-1]
            found = []
            for kind, rx in _CLAUSES:
                for m in rx.finditer(seg):
                    if not any(m.start() < e and s < m.end() for s, e, *_ in found):
                        found.append((m.start(), m.end(), kind, m))
            found.sort(key=lambda x: x[0])
            prev = 0
            for s, e, kind, m in found:
                scope = seg[prev:s]
                cut = max(scope.rfind(x) for x in "；。")
                scope = scope[cut + 1:] if cut >= 0 else scope
                if si == 0 and prev == 0 and "公布" in scope:  # clause glued to the promulgation article list
                    scope = scope[scope.rfind("條文") + 2:] if "條文" in scope else ""
                scope = scope.split("但")[-1]
                prev = e
                if re.search(r"原(?:中華民國)?" + _N + r"年" + _N + r"月" + _N + r"日", scope):
                    continue  # "原一百零八年…修正公布之第19-1條施行期間…": about an EARLIER amendment, not this one
                eff, basis = _clause_date(kind, m, promulgated)
                if si and eff != PENDING:
                    basis = "executive_yuan_order" if basis in ("explicit", "explicit_tax_year") else basis
                whole, part, para_only = _refs(scope)
                clauses.append({"seg": si, "clause": m.group(0), "scope": scope, "effective": eff, "basis": basis})
                if whole:
                    for r in whole:
                        if eff != PENDING or r not in rules:  # a later order dates a pending article
                            rules[r] = (eff, basis)
                elif part or para_only:
                    partial.append({"refs": part, "effective": eff, "basis": basis, "scope": scope[-40:]})
                elif eff == PENDING:
                    delegated = True
                else:  # no article named: the whole amendment (a later clause / order wins)
                    main, main_basis = eff, basis
        if main is None:
            dated = [v for v in rules.values() if v[0] != PENDING]
            if delegated and dated:  # orders name articles but give no date for "the rest"
                main, main_basis = min(v[0] for v in dated), "executive_yuan_order_unnamed"
            elif delegated:
                main, main_basis = None, "by_executive_yuan_unknown"  # date set later by an order not in this entry
            elif dated and len(segs) > 1:  # an order dates the amended article(s); same date for the rest
                main, main_basis = min(v[0] for v in dated), "executive_yuan_order_unnamed"
            else:
                main, main_basis = (promulgated + dt.timedelta(days=2)).isoformat(), "default_§13"
        arts = re.search(r"公布第\s*([\d\s、～\-－之]+?)\s*條", c)
        out.append({
            "no": no,
            "promulgated": promulgated.isoformat(),
            "effective": main,
            "effective_basis": main_basis,
            "whole_text": "全文" in c[:80],
            "articles": [a.strip() for a in re.split(r"[、\s]+", arts.group(1)) if a.strip()] if arts else [],
            "note": c,
            "rules": [{"ref": r, "effective": v[0], "basis": v[1]} for r, v in rules.items()],
            "partial": partial,
            "delegated": delegated,
            # delegated, orders date only the articles they name: an article that no order names has no date here
            "rest_undated": delegated and main_basis == "executive_yuan_order_unnamed",
            "clauses": clauses,
        })
    return sorted(out, key=lambda e: e["promulgated"])
