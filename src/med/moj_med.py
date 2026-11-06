"""MOJ amendment history (法規沿革) parser for ChronoMed-TW = moj_history.parse + the commencement forms health law uses.

The tax parser (src/moj_history.py) takes the LAST "自<date>施行" in an entry as the date of the whole amendment, and
otherwise applies 中央法規標準法 §13 (promulgation + 2 days). That was enough for tax acts. Health acts use more forms:
  relative      本法自公布後六個月施行 / 自公布後二年施行 / 自公布日起六個月施行      -> promulgation + N months/years
  exceptions    除第26條、第27條，自公布後一年施行外，自公布日施行                     -> per-article dates; the LAST date
                (食品安全衛生管理法 2014-02-05: the tax rule would date the whole amendment 2014-06-19, but only parts of
                Art. 22 and 30 started then; the rest started on promulgation)
  EY orders     …令發布第27、28、35條條文定自一百零一年七月一日施行 …令發布除已施行之條文外，定自一百零二年一月一日施行
                (全民健康保險法 2011 "二代健保": Arts 27/28/35 from 2012-07-01, the rest from 2013-01-01)
  chapters      第四章之一 / 第五章 named in an order                                  -> every article of that chapter
  paragraphs    第4條第1項第4款 / 第30條申報制度                                       -> recorded as PARTIAL (the store is
                article-level: the article keeps the main date and is flagged)
  pending       施行日期由行政院定之 with no order yet                                 -> PENDING (not in force)
  other forms   於<date>施行, 同年七月二十日施行, 施行之日（一百零六年六月三日）施行
MOJ wraps lines at a fixed width, splitting words and numbers ("定自 一百年", "880016212 0"); all whitespace is removed
before parsing. Output keeps the keys of moj_history.parse (no, promulgated, effective, effective_basis, whole_text,
articles, note) and adds: rules (whole-article / chapter dates), partial, pending_refs, is_promulgation.
"""
import datetime as dt
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402,F401  (sets sys.path and dont_write_bytecode)
from moj_history import _ROC_DATE, cn_num, roc_date  # noqa: E402  (original helpers, reused)

PENDING = "pending"
_N = r"[〇零一二三四五六七八九十百\d]+"
_DATE = _ROC_DATE  # (?:中華民國)?Y年M月D日 (Chinese or Arabic numerals)
ENTRY_RX = re.compile(r'<div class="col-data text-pre">(.*?)</div>', re.S)
# clause patterns, applied to whitespace-free text; each yields a date spec
CLAUSES = [
    ("abs", re.compile(r"(?:定)?(?:自|於)" + _DATE + r"(?:起)?施行")),
    ("abs", re.compile(r"（" + _DATE + r"）(?:起)?施行")),
    ("same_year", re.compile(r"同年(" + _N + r")月(" + _N + r")日(?:起)?施行")),
    ("tax_year", re.compile(r"(?:定)?自(?:中華民國)?(" + _N + r")年度(?:起)?施行")),  # tax acts: "自一百零七年度施行"
    ("rel", re.compile(r"自(?:公布|發布)(?:日起|後)(" + _N + r")(年|個月|日)(?:起)?施行")),
    ("same_day", re.compile(r"自(?:公布|發布)(?:之)?日(?:起)?施行")),
    ("ey", re.compile(r"(?:其)?(?:施行日期，?)?由行政院(?:以命令|會同[^，；。]{0,8}?)?定之")),
]
ART_RX = re.compile(r"第([\d\-、～]+)條((?:第[\d、～]+[項款目])*)")
CHAP_RX = re.compile(r"第([〇一二三四五六七八九十百]+)章(?:之([〇一二三四五六七八九十]+))?")
WHOLE_AFTER = ("條文", "、", "，", "及", "與", "和", "；", "定", "自", "之施行", "施行", "其施行", "）", "或",
               "增訂條文", "修正條文", "規定，", "規定自", "規定。", "外")


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return dt.date(y, m, day)
        except ValueError:
            continue
    raise ValueError(d)


def _cn_art(num: str) -> str:
    """'92-1' -> '第九十二條之一' (LY article key), using english.cn (original helper)."""
    from english import cn
    a, _, b = num.partition("-")
    return f"第{cn(int(a))}條" + (f"之{cn(int(b))}" if b else "")


def refs(text: str) -> dict:
    """Article / chapter references in a clause's reference text. Whole articles vs paragraph-level (partial)."""
    whole, partial, chapters = [], [], []
    text = re.sub(r"依第[\d\-]+條?規定[：:，]?", "", text)  # "依第91條規定：" names the commencement article itself
    text = re.sub(r"除[^外，；]*?外", "", text)  # "除第16、20條外，其餘修正之第2…條" -> 16 and 20 are EXCLUDED
    for m in ART_RX.finditer(text):
        before = text[:m.start()]
        if before.endswith(("法", "例")) and not before.endswith(("本法", "本條例")):
            continue  # "藥事法第27-3條": an article of ANOTHER act
        nums = []
        for tok in m.group(1).split("、"):
            if "～" in tok:
                a, b = tok.split("～")
                if a.isdigit() and b.isdigit():
                    nums += [str(i) for i in range(int(a), int(b) + 1)]
                else:
                    nums += [a, b]
            elif tok:
                nums.append(tok)
        after = text[m.end():]
        is_whole = not m.group(2) and (after in ("", "之") or after.startswith(WHOLE_AFTER))
        (whole if is_whole else partial).extend(_cn_art(n) for n in nums if re.fullmatch(r"\d+(?:-\d+)?", n))
    for m in CHAP_RX.finditer(text):
        chapters.append("第" + m.group(1) + "章" + (f"之{m.group(2)}" if m.group(2) else ""))
    return {"whole": whole, "partial": partial, "chapters": chapters}


def clauses(text: str, prom: dt.date) -> list[dict]:
    """Every commencement clause in `text` (left to right) with the reference text that precedes it."""
    found = []
    for kind, rx in CLAUSES:
        for m in rx.finditer(text):
            if any(not (m.end() <= s or m.start() >= e) for s, e, *_ in found):
                continue  # overlaps a clause found by an earlier (more specific) pattern
            found.append((m.start(), m.end(), kind, m))
    found.sort()
    out, prev = [], 0
    for s, e, kind, m in found:
        if kind == "abs":
            eff, basis = roc_date(m).isoformat(), "explicit"
        elif kind == "same_year":
            eff, basis = dt.date(prom.year, cn_num(m.group(1)), cn_num(m.group(2))).isoformat(), "explicit"
        elif kind == "tax_year":
            eff, basis = dt.date(cn_num(m.group(1)) + 1911, 1, 1).isoformat(), "tax_year"
        elif kind == "rel":
            n, unit = cn_num(m.group(1)), m.group(2)
            d = add_months(prom, 12 * n) if unit == "年" else add_months(prom, n) if unit == "個月" else prom + dt.timedelta(days=n)
            eff, basis = d.isoformat(), "relative_after_promulgation"
        elif kind == "same_day":
            eff, basis = (prom + dt.timedelta(days=2)).isoformat(), "default_§13"
        else:
            eff, basis = PENDING, "by_executive_yuan"
        out.append({"ref_text": text[prev:s], "effective": eff, "basis": basis, "clause": m.group(0)})
        prev = e
    return out


SPLIT_RX = re.compile(r"(?=中華民國" + _N + r"年" + _N + r"月" + _N + r"日(?:行政院|司法院|總統|考試院))")


def parse_entry(raw: str) -> dict:
    t = re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", raw)))
    no = int(re.match(r"(\d+)", t).group(1))
    prom = roc_date(re.search(_DATE, t))
    segs = [s for s in SPLIT_RX.split(t) if s]
    if re.fullmatch(r"\d+\.", segs[0]) and len(segs) > 1:
        head, orders = segs[1], segs[2:]
    else:
        head, orders = segs[0], segs[1:]
    is_prom = "公布" in head
    # promulgation segment: drop the "修正公布第…條條文；並增訂…；刪除…" article lists, keep the commencement sentence(s).
    # A clause glued to a list ("…並增訂第41-1條條文同年七月二十日施行") is kept from the clause on: the list before it
    # names the amended articles, not articles with a special date.
    keep = []
    for i, p in enumerate(head.split("；")):
        if i == 0 or re.match(r"(?:並)?(?:增訂|刪除|修正|制定)", p):
            starts = [m.start() for _, rx in CLAUSES for m in [rx.search(p)] if m]
            if starts:
                keep.append(p[min(starts):])
            continue
        keep.append(p)
    comm = "；".join(keep)
    comm = re.sub(r"（原名稱：.*?）", "", comm)
    version_eff, version_basis = None, "default_§13"
    rules, partial, pending_refs = [], [], []

    def absorb(cls: list[dict], from_order: bool) -> None:
        nonlocal version_eff, version_basis
        for c in cls:
            r = refs(c["ref_text"])
            basis = ("executive_yuan_order" if from_order else c["basis"]) if c["effective"] != PENDING else c["basis"]
            if r["whole"] or r["chapters"]:
                rules.append({"articles": sorted(set(r["whole"])), "chapters": r["chapters"], "effective": c["effective"],
                              "basis": basis, "source": "history_order" if from_order else "history"})
            if r["partial"]:
                partial.append({"articles": sorted(set(r["partial"])), "effective": c["effective"], "basis": basis,
                                "ref": c["ref_text"][-60:]})
            if not (r["whole"] or r["chapters"] or r["partial"]):
                # no article named: the whole amendment ("其餘條文", "除已施行之條文外", "本法", or nothing)
                if c["effective"] == PENDING and from_order:
                    continue
                if c["effective"] != PENDING or version_eff is None:
                    version_eff, version_basis = c["effective"], basis

    unparsed = []  # text that mentions 施行 but yields no clause: counted, never guessed
    cls = clauses(comm, prom)
    if "施行" in comm and not cls:
        unparsed.append(comm)
    absorb(cls, from_order=False)
    n_orders = 0
    for o in orders:
        # competent-authority announcements (…號公告 …自一百零二年七月二十三日起改由「衛生福利部」管轄) have no 號令/號函
        body = re.split(r"號(?:令|函)(?:、[^；]*?號令)?(?:會同)?(?:發布)?", o, maxsplit=1)
        if len(body) < 2 or "施行" not in body[1]:
            continue
        n_orders += 1
        cls = clauses(body[1], prom)
        if not cls:
            unparsed.append(body[1])
        absorb(cls, from_order=True)
    # a pending item stays pending only if no later order dated all of it
    dated_a = {a for r in rules if r["effective"] != PENDING for a in r["articles"]}
    dated_c = {c for r in rules if r["effective"] != PENDING for c in r["chapters"]}
    for r in rules:
        if r["effective"] == PENDING and not (set(r["articles"]) <= dated_a and set(r["chapters"]) <= dated_c):
            pending_refs.append({**r, "articles": sorted(set(r["articles"]) - dated_a),
                                 "chapters": [c for c in r["chapters"] if c not in dated_c]})
    partial = [p for p in partial if p["effective"] != PENDING or not set(p["articles"]) <= {
        a for q in partial if q["effective"] != PENDING for a in q["articles"]}]
    if version_eff is None:
        version_eff, version_basis = (prom + dt.timedelta(days=2)).isoformat(), "default_§13"
    arts = re.search(r"公布第([\d、～\-之]+?)條", t)
    return {
        "no": no,
        "promulgated": prom.isoformat(),
        "effective": None if version_eff == PENDING else version_eff,
        "effective_basis": "pending_executive_yuan" if version_eff == PENDING else version_basis,
        "whole_text": "全文" in head[:80],
        "articles": [a for a in re.split(r"[、]", arts.group(1)) if a] if arts else [],
        "note": t,
        "commencement_text": comm,
        "rules": [r for r in rules if r["effective"] != PENDING],
        "pending_refs": pending_refs,
        "partial": partial,
        "is_promulgation": is_prom,
        "unparsed": unparsed,
        "n_orders": n_orders,
    }


def page(pcode: str) -> str:
    """The cached MOJ history page (data/med/raw/moj); never fetches (run fetch_med.py history first)."""
    return (medcfg.RAW_MOJ / f"{pcode}-history.html").read_text(encoding="utf-8", errors="ignore")


def parse(page: str) -> list[dict]:
    blocks = ENTRY_RX.findall(page)
    out = [parse_entry(b) for b in blocks if re.match(r"\s*\d+\s*\.\s*中華民國", html.unescape(re.sub(r"<[^>]+>", "", b)))]
    return sorted(out, key=lambda e: (e["promulgated"], e["no"]))


if __name__ == "__main__":
    import json
    sys.stdout.reconfigure(encoding="utf-8")
    page = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
    for e in parse(page):
        print(json.dumps({k: v for k, v in e.items() if k != "note"}, ensure_ascii=False))
