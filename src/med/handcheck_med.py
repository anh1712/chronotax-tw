"""Hand-checks of well-known commencement cases against the official MOJ pages, and a current-text cross-check.

  python -I src/med/handcheck_med.py   -> data/med/results/handcheck.json

For each case: the official MOJ amendment-history entry (cached page, whitespace removed; URL given), the dates a
reader gets from that entry (written below by hand, with the words they come from), and what each store returns:
ChronoMed (data/med/medtw.db) and the unchanged tax rules (data/med/medtw_taxparser.db).
Cross-check: every article of each act's current MOJ text (law.moj.gov.tw LawAll page, cached by fetch_med.py)
against the newest LY version text (whitespace removed before comparing).
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402
from medcfg import DB, MED, RAW_LY, RAW_MOJ_ALL, RESULTS, write_atomic  # noqa: E402
import moj_med  # noqa: E402
import registry_med  # noqa: E402

TP = MED / "medtw_taxparser.db"
HIST = "https://law.moj.gov.tw/LawClass/LawHistory.aspx?pcode={}"

CASES = [
    {"id": "nhi_2g", "law_id": "01189", "pcode": "L0060001", "entry": 9, "ly_version": "01189:2011-01-04-全文修正",
     "title": "National Health Insurance Act, 2011 full revision ('二代健保')",
     "reading": "promulgated 2011-01-26; Executive Yuan order of 2012-05-21: Arts 27, 28, 35 from 2012-07-01 "
                "('發布第27、28、35條條文定自一百零一年七月一日施行'); order of 2012-10-09: all other articles from "
                "2013-01-01 ('除已施行之條文外，定自一百零二年一月一日施行')",
     "expect": {"第二十七條": "2012-07-01", "第二十八條": "2012-07-01", "第三十五條": "2012-07-01",
                "第十一條": None, "*": "2013-01-01"}},
    {"id": "nhi_2011_art11", "law_id": "01189", "pcode": "L0060001", "entry": 10, "ly_version": "01189:2011-06-10-修正",
     "title": "National Health Insurance Act, 2011-06-29 amendment of Art. 11 (of the new, not yet active text)",
     "reading": "promulgated 2011-06-29; '施行日期，由行政院定之' + Executive Yuan order of 2011-08-12: '定自一百年九月一日施行' "
                "-> 2011-09-01. This text replaced the 2011-01 text of Art. 11 before that text ever applied.",
     "expect": {"第十一條": "2011-09-01", "*": "2011-09-01"}},
    {"id": "tobacco_2023", "law_id": "02549", "pcode": "L0070021", "entry": 5, "ly_version": "02549:2023-01-12-全文修正",
     "title": "Tobacco Hazards Prevention Act, 2023 full revision",
     "reading": "promulgated 2023-02-15; Executive Yuan order of 2023-03-20: Art. 4 para. 1 item 4 from 2023-04-01; "
                "Art. 9 para. 2 and part of Art. 29 from 2024-03-22; all other provisions ('其餘條文') from 2023-03-22",
     "expect": {"*": "2023-03-22"}, "paragraph_exceptions": ["第四條", "第九條", "第二十九條"]},
    {"id": "tobacco_2007", "law_id": "02549", "pcode": "L0070021", "entry": 3, "ly_version": "02549:2007-06-15-全文修正",
     "title": "Tobacco Hazards Prevention Act, 2007 full revision",
     "reading": "promulgated 2007-07-11; '除第4條之施行日期，由行政院定之外，自公布後十八個月施行' -> 2009-01-11 for all "
                "articles except Art. 4 (date left to the Executive Yuan; Art. 4 was amended again in 2009 and that text "
                "started 2009-06-01, entry 4). The current Art. 16 itself says '本法中華民國九十八年一月十一日修正生效前'.",
     "expect": {"第四條": None, "*": "2009-01-11"}},
    {"id": "devices_2021", "law_id": "07121", "pcode": "L0030106", "entry": 1, "ly_version": "07121:2019-12-13-制定",
     "title": "Medical Devices Act, enactment",
     "reading": "promulgated 2020-01-15; Executive Yuan order of 2021-02-17: in force from 2021-05-01 "
                "('定自一百十年五月一日施行')",
     "expect": {"*": "2021-05-01"}},
    {"id": "autonomy_2019", "law_id": "02536", "pcode": "L0020189", "entry": 1, "ly_version": "02536:2015-12-18-制定",
     "title": "Patient Right to Autonomy Act, enactment",
     "reading": "promulgated 2016-01-06; '依第19條規定：自公布後三年施行' -> 2019-01-06",
     "expect": {"*": "2019-01-06"}},
]


def ro(p):
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def check_case(case, med, tp) -> dict:
    entry = next(e for e in moj_med.parse(moj_med.page(case["pcode"])) if e["no"] == case["entry"])
    out = {k: case[k] for k in ("id", "title", "reading")}
    out["moj_url"] = HIST.format(case["pcode"])
    out["moj_entry_text"] = entry["note"]
    for name, con in (("chronomed", med), ("tax_rules", tp)):
        rows = con.execute("SELECT article_no, valid_from, valid_to, overtaken, from_basis, flag FROM article_version "
                           "WHERE law_id=? AND first_ly_version=? AND deleted=0" if name == "chronomed" else
                           "SELECT article_no, valid_from, valid_to, overtaken, from_basis, NULL AS flag FROM "
                           "article_version WHERE law_id=? AND first_ly_version=? AND deleted=0",
                           (case["law_id"], case["ly_version"])).fetchall()
        ok, wrong, notes = 0, [], []
        for r in rows:
            exp = case["expect"].get(r["article_no"], case["expect"]["*"])
            if exp is None:  # expected: never in force on its own
                good = r["overtaken"] == 1 or r["valid_to"] == r["valid_from"]
            elif r["overtaken"]:
                good = False
                notes.append(f"{r['article_no']} overtaken (zero-length): a later amendment of the same article "
                             f"started first")
            else:
                good = r["valid_from"] == exp
            ok += good
            if not good:
                wrong.append((r["article_no"], r["valid_from"], exp))
        pending = []
        if name == "chronomed":
            pending = [r[0] for r in con.execute("SELECT article_no FROM pending_article WHERE law_id=? AND ly_version=?",
                                                 (case["law_id"], case["ly_version"]))]
            if "第四條" in pending and case["id"] == "tobacco_2007":
                ok += 1  # Art. 4: correctly never put in force (gap row until the 2009 text starts)
        flags = [r["article_no"] for r in rows if r["flag"] and "partial" in r["flag"]]
        out[name] = {"article_versions": len(rows) + len(pending), "as_expected": ok,
                     "not_as_expected": wrong, "pending_not_in_force": pending, "flagged_partial": flags,
                     "notes": notes}
    return out


PUNCT = str.maketrans({"(": "（", ")": "）", ":": "：", "︰": "：", ";": "；", ",": "，"})


def norm(t: str) -> str:
    """Whitespace removed; half-width brackets/colons mapped to the full-width forms (pure typography)."""
    return re.sub(r"\s+", "", t).translate(PUNCT)


def current_text_check() -> dict:
    """MOJ current text (LawAll page) vs the newest LY version, article by article."""
    res, tot_eq, tot = {}, 0, 0
    codes = registry_med.pcodes()
    for lid, (name, _) in registry_med.laws().items():
        page = (RAW_MOJ_ALL / f"{codes[lid]}.html").read_text(encoding="utf-8", errors="ignore")
        moj = {}
        for no, body in re.findall(r'flno=([\d\-]+)" name="[\d\-]+">第 [\d\-]+ 條</a></div><div class="col-data">'
                                   r'<div class="law-article">(.*?)</div>\s*</div></div>', page, re.S):
            lines = re.findall(r'<div class="line-\d+[^"]*">(.*?)</div>', body, re.S)
            moj[moj_med._cn_art(no)] = norm(re.sub(r"<[^>]+>", "", "".join(lines)))
        meta = json.loads((RAW_LY / lid / "_law.json").read_text(encoding="utf-8"))
        last = sorted(meta["versions"], key=lambda v: v["日期"])[-1]
        rows = json.loads((RAW_LY / lid / (last["版本編號"].split(":", 1)[1] + ".json")).read_text(encoding="utf-8"))
        ly = {r["條號"]: norm(r.get("內容") or "") for r in rows
              if (r.get("條號") or "").startswith("第") and (r.get("內容") or "").strip()}
        both = set(moj) & set(ly)
        eq = sum(moj[a] == ly[a] for a in both)
        import difflib
        res[name] = {"moj_articles": len(moj), "ly_articles": len(ly), "in_both": len(both), "identical": eq,
                     "differ": sorted(a for a in both if moj[a] != ly[a]),
                     "differences": {a: [(op, ly[a][i1:i2], moj[a][j1:j2]) for op, i1, i2, j1, j2 in
                                         difflib.SequenceMatcher(None, ly[a], moj[a], autojunk=False).get_opcodes()
                                         if op != "equal"][:5] for a in sorted(both) if moj[a] != ly[a]},
                     "only_moj": sorted(set(moj) - set(ly)), "only_ly": sorted(set(ly) - set(moj))}
        tot_eq += eq
        tot += len(both)
    return {"identical": tot_eq, "compared": tot, "per_act": res}


def main() -> None:
    med, tp = ro(DB), ro(TP)
    out = {"cases": [check_case(c, med, tp) for c in CASES], "current_text": current_text_check()}
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_atomic(RESULTS / "handcheck.json", json.dumps(out, ensure_ascii=False, indent=1))
    for c in out["cases"]:
        print("==", c["id"], "|", c["title"])
        for s in ("chronomed", "tax_rules"):
            r = c[s]
            print(f"   {s:9s}: {r['as_expected']}/{r['article_versions']} as expected; not: {r['not_as_expected'][:6]} "
                  f"pending: {r['pending_not_in_force']} partial: {r['flagged_partial']} {r['notes']}")
    ct = out["current_text"]
    print("current text identical:", ct["identical"], "/", ct["compared"])
    for k, v in ct["per_act"].items():
        if v["differ"] or v["only_moj"] or v["only_ly"]:
            print("  ", k, {kk: v[kk] for kk in ("moj_articles", "ly_articles", "identical", "differences", "only_moj", "only_ly")})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
