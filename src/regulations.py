"""Enforcement rules and regulations (施行細則, 辦法) from the MOJ database — CURRENT text only.

LYAPI covers acts passed by the Legislative Yuan, not executive regulations, and the MOJ site shows only the current
text of a regulation plus a textual history. So each regulation is loaded as ONE version valid from its latest
amendment date, with from_basis = 'moj_current_only': the system can quote it for questions about the present, and the
UI/answers must not present it as the text of earlier years. Run after build_db.py (it appends to data/lawtw.db).
"""
import html
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import english  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "lawtw.db"
RAW = ROOT / "data" / "raw" / "moj_reg"
UA = {"User-Agent": "LAW-TW research prototype"}

REGS = {  # MOJ pcode → (title, English title)
    "G0340004": ("所得稅法施行細則", "Enforcement Rules of the Income Tax Act"),
    "G0340081": ("加值型及非加值型營業稅法施行細則", "Enforcement Rules of the Value-added and Non-value-added Business Tax Act"),
    "G0340082": ("統一發票使用辦法", "Regulations Governing the Use of Uniform Invoices"),
    "G0340039": ("稅捐稽徵法施行細則", "Enforcement Rules of the Tax Collection Act"),
    "G0340073": ("遺產及贈與稅法施行細則", "Enforcement Rules of the Estate and Gift Tax Act"),
}


def fetch(pcode: str) -> str:
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / f"{pcode}.html"
    if not f.exists():
        url = f"https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode={pcode}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            f.write_bytes(r.read())
        time.sleep(1)
    return f.read_text(encoding="utf-8", errors="ignore")


def roc_to_iso(s: str) -> str | None:
    m = re.search(r"民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", s)
    return f"{int(m.group(1)) + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def parse(page: str) -> tuple[str | None, list[tuple[str, str]]]:
    amended = re.search(r"修正日期：</th>\s*<td[^>]*>(.*?)</td>", page, re.S)
    amended = roc_to_iso(re.sub(r"<[^>]+>", "", amended.group(1))) if amended else None
    out = []
    for seg in page.split('<div class="row"><div class="col-no">')[1:]:
        m = re.search(r'name="([\d-]+)">第 [\d-]+ 條', seg)
        if not m:
            continue
        flno, body = m.group(1), seg
        lines = re.findall(r'<div class="line-\d+[^"]*">(.*?)</div>', body, re.S)
        text = "\n".join(html.unescape(re.sub(r"<[^>]+>", "", ln)).strip() for ln in lines)
        main, _, sub = flno.partition("-")
        art = f"第{english.cn(int(main))}條" + (f"之{english.cn(int(sub))}" if sub else "")
        if text:
            out.append((art, text))
    return amended, out


def main() -> None:
    con = sqlite3.connect(DB)
    for pcode, (title, title_en) in REGS.items():
        amended, rows = parse(fetch(pcode))
        con.execute("DELETE FROM article_version WHERE law_id=?", (pcode,))
        con.execute("INSERT OR REPLACE INTO law VALUES(?,?,?,?)", (pcode, title, title_en, pcode))
        con.execute("INSERT OR REPLACE INTO version(law_id, ly_version, ly_date, action, promulgated, effective, "
                    "effective_basis, moj_note) VALUES(?,?,?,?,?,?,?,?)",
                    (pcode, f"{pcode}:{amended}-current", amended, "現行", amended, amended, "moj_current_only",
                     "MOJ current text; earlier versions not available from this source"))
        for i, (art, text) in enumerate(rows):
            con.execute("INSERT INTO article_version(law_id, article_no, seq, chapter, text, first_ly_version, "
                        "valid_from, valid_to, from_basis, published, retro, deleted) VALUES(?,?,?,?,?,?,?,?,?,?,0,0)",
                        (pcode, art, i, None, text, f"{pcode}:{amended}-current", amended, None, "moj_current_only",
                         amended))
        # official English, when MOJ has it
        try:
            en_date, en_rows = english.parse(english.fetch(pcode))
            for label, t in en_rows:
                no = english.article_no(label)
                if no:
                    con.execute("INSERT OR REPLACE INTO article_en VALUES(?,?,?,?,?)", (pcode, no, label, t, en_date))
        except Exception as e:
            en_rows = []
            print(pcode, "no English:", e)
        print(f"{pcode} {title}: {len(rows)} articles, current since {amended}, English {len(en_rows)}")
    con.execute("INSERT INTO article_fts(article_fts) VALUES('rebuild')")
    con.execute("INSERT INTO article_en_fts(article_en_fts) VALUES('rebuild')")
    con.commit()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
