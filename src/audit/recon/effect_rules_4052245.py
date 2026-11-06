"""Per-article effective dates from an act's own commencement article (施行條文).

Taiwanese acts keep a cumulative commencement article (e.g. 所得稅法 第一百二十六條) that lists, amendment by amendment,
when each change took effect — often different dates for different articles of the same amendment:

  本法中華民國一百零七年二月七日修正公布條文，自一百零七年一月一日施行。但第五條、…及第一百十條，自一百零七年度施行，
  第七十三條之二自一百零八年一月一日施行。
  …一百零三年六月四日修正公布條文，除第六十六條之四、第六十六條之六及第七十三條之二自一百零四年一月一日施行外，
  其餘條文自一百零四年度施行。
  …一百十五年八月二十一日修正之條文，自一百十五年一月一日施行。   ← keyed by passage date, not promulgation

parse() turns that into rules {amend_date, articles|None (=all), effective, basis}; lookup() answers
"when did article A of the amendment dated D take effect?". Unparsed sentences are kept so coverage can be measured.
Never guesses: an article not named by any rule falls back to the amendment-level date chosen by the caller.
"""
import datetime as dt
import re

from moj_history import _ROC_DATE, cn_num, roc_date

_CN = "〇零一二三四五六七八九十百"
ART_RX = re.compile(rf"第([{_CN}]+)條(之([{_CN}]+))?")
# "自一百零七年一月一日施行" | "自一百零七年度施行" | "自九十九年度施行"
EFF_RX = re.compile(rf"自(?:中華民國)?(?:{_ROC_DATE[len('(?:中華民國)?'):]}|([{_CN}\d]+)年度)(?:起)?施行")
AMEND_RX = re.compile(rf"{_ROC_DATE}(?:修正公布|修正|制定公布|公布)")


def art_key(m: re.Match) -> str:
    return f"第{m.group(1)}條" + (f"之{m.group(3)}" if m.group(2) else "")


def _eff(m: re.Match) -> tuple[str, str]:
    if m.group(4):  # tax-year form: applies from that income year → Jan 1, flagged
        return dt.date(cn_num(m.group(4)) + 1911, 1, 1).isoformat(), "commencement_tax_year"
    return dt.date(cn_num(m.group(1)) + 1911, cn_num(m.group(2)), cn_num(m.group(3))).isoformat(), "commencement_article"


def parse(text: str) -> dict:
    rules, unparsed = [], []
    text = text.replace("　", "").replace("\n", "")
    last_amend = None  # "…修正公布條文，自…施行。但第五條…" — the 但 sentence inherits the previous amendment
    for sent in re.split(r"[。；]", text):
        if not sent.strip():
            continue
        amends = list(AMEND_RX.finditer(sent))
        effs = list(EFF_RX.finditer(sent))
        if not amends and sent.startswith("但") and last_amend and effs:
            for seg in re.split(r"，(?=第)", sent[1:]):
                es = EFF_RX.search(seg)
                arts = sorted({art_key(m) for m in ART_RX.finditer(seg[: es.start()] if es else seg)})
                if es and arts:
                    rules.append({"amend_date": last_amend, "articles": arts, "effective": _eff(es)[0], "basis": _eff(es)[1]})
                elif arts:
                    unparsed.append(seg)
            continue
        if not amends or (not effs and "行政院定之" not in sent):
            if amends or effs:
                unparsed.append(sent)
            continue
        if "行政院定之" in sent and not effs:  # several amendments, dates set later by Executive Yuan orders
            for a in amends:
                rules.append({"amend_date": roc_date(a).isoformat(), "articles": None, "effective": None,
                              "basis": "commencement_by_executive_yuan"})
            continue
        amend = roc_date(amends[-1]).isoformat()
        last_amend = amend
        head = sent[amends[-1].end():]
        # "除第A、第B及第C自D施行外，其餘條文自E施行"
        if "除" in head and "其餘" in head:
            exc, rest = head.split("其餘", 1)
            e1 = EFF_RX.search(exc)
            e2 = EFF_RX.search(rest)
            if e1:
                rules.append({"amend_date": amend, "articles": sorted({art_key(m) for m in ART_RX.finditer(exc)}),
                              "effective": _eff(e1)[0], "basis": _eff(e1)[1]})
            if e2:
                rules.append({"amend_date": amend, "articles": None, "effective": _eff(e2)[0], "basis": _eff(e2)[1]})
            continue
        # "修正公布之第十七條，自…施行" | "修正公布條文，自…施行。但第X、Y，自…施行，第Z自…施行"
        main, _, but = head.partition("但")
        e = EFF_RX.search(main)
        if e:
            arts = sorted({art_key(m) for m in ART_RX.finditer(main[: e.start()])}) or None
            rules.append({"amend_date": amend, "articles": arts, "effective": _eff(e)[0], "basis": _eff(e)[1]})
        for seg in re.split(r"，(?=第)", but) if but else []:
            es = EFF_RX.search(seg)
            arts = sorted({art_key(m) for m in ART_RX.finditer(seg[: es.start()] if es else seg)})
            if es and arts:
                rules.append({"amend_date": amend, "articles": arts, "effective": _eff(es)[0], "basis": _eff(es)[1]})
            elif arts:
                unparsed.append(seg)
    return {"rules": rules, "unparsed": unparsed}


def lookup(rules: list[dict], amend_dates: set[str], article: str) -> tuple[str | None, str] | None:
    """Rule for `article` in the amendment identified by any of `amend_dates` (promulgation or passage date).
    Article-specific rules win over whole-amendment rules. Returns (effective|None, basis) or None if no rule."""
    hits = [r for r in rules if r["amend_date"] in amend_dates]
    for r in hits:
        if r["articles"] and article in r["articles"]:
            return r["effective"], r["basis"]
    for r in hits:
        if r["articles"] is None:
            return r["effective"], r["basis"]
    return None


def find_commencement(rows: list[dict]) -> str | None:
    """The last article whose text is about commencement (施行)."""
    for r in reversed(rows):
        t = (r.get("內容") or "")
        if r.get("條號", "").startswith("第") and "施行" in t and ("本法" in t or "本條例" in t):
            return t
    return None
