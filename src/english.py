"""Official English translations (MOJ Laws & Regulations Database, ENG) as a gloss for article versions.

The English text exists for the CURRENT version only (MOJ: "if they differ, the Chinese text prevails"), so it is
attached to the article, with the date of the amendment it reflects; the UI must label it as a gloss of the current
text, not of a historical version.
  python src/english.py   → data/raw/moj_en/<pcode>.html, table article_en in data/lawtw.db
"""
import html
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import LAWS, pcodes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "moj_en"
DB = ROOT / "data" / "lawtw.db"
UA = {"User-Agent": "LAW-TW research prototype"}
_D = "〇一二三四五六七八九"


def cn(n: int) -> str:
    """17 → 十七, 105 → 一百零五, 110 → 一百十, 126 → 一百二十六 (MOJ / LY article numbering style)."""
    if n < 10:
        return _D[n]
    if n < 20:
        return "十" + (_D[n % 10] if n % 10 else "")
    if n < 100:
        return _D[n // 10] + "十" + (_D[n % 10] if n % 10 else "")
    h, r = divmod(n, 100)
    if r == 0:
        return _D[h] + "百"
    if r < 10:
        return _D[h] + "百零" + _D[r]
    if r < 20:
        return _D[h] + "百" + "十" + (_D[r % 10] if r % 10 else "")
    return _D[h] + "百" + cn(r)


def article_no(en: str) -> str | None:
    m = re.fullmatch(r"Article\s+(\d+)(?:-(\d+))?", en.strip())
    if not m:
        return None
    return f"第{cn(int(m.group(1)))}條" + (f"之{cn(int(m.group(2)))}" if m.group(2) else "")


def fetch(pcode: str) -> str:
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / f"{pcode}.html"
    if not f.exists():
        url = f"https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode={pcode}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            f.write_bytes(r.read())
        time.sleep(1)
    return f.read_text(encoding="utf-8", errors="ignore")


def parse(page: str) -> tuple[str | None, list[tuple[str, str]]]:
    date = re.search(r"Amended Date：</th>\s*<td[^>]*>\s*([^<]+)", page)
    rows = re.findall(r'<div class="col-no">([^<]+)</div><div class="col-data">(.*?)</div></div>', page, re.S)
    out = []
    for no, body in rows:
        text = html.unescape(re.sub(r"<br\s*/?>", "\n", body))
        text = re.sub(r"<[^>]+>", "", text).strip()
        out.append((no.strip(), text))
    return (date.group(1).strip() if date else None), out


def main() -> None:
    con = sqlite3.connect(DB)
    con.execute("DROP TABLE IF EXISTS article_en")
    con.execute("CREATE TABLE article_en(law_id TEXT, article_no TEXT, label TEXT, text TEXT, en_amended TEXT,"
                " PRIMARY KEY(law_id, article_no))")
    codes = pcodes()
    for law_id in LAWS:
        try:
            date, rows = parse(fetch(codes[law_id]))
        except Exception as e:  # keep going; report
            print(law_id, "fetch failed:", e)
            continue
        mapped = 0
        for label, text in rows:
            no = article_no(label)
            if no:
                con.execute("INSERT OR REPLACE INTO article_en VALUES(?,?,?,?,?)", (law_id, no, label, text, date))
                mapped += 1
        known = con.execute("SELECT count(DISTINCT article_no) FROM article_version WHERE law_id=? AND valid_to IS NULL "
                            "AND deleted=0", (law_id,)).fetchone()[0]
        joined = con.execute("SELECT count(*) FROM article_en e JOIN article_version v ON v.law_id=e.law_id AND "
                             "v.article_no=e.article_no AND v.valid_to IS NULL AND v.deleted=0 WHERE e.law_id=?",
                             (law_id,)).fetchone()[0]
        print(f"{law_id} {LAWS[law_id][1]}: English amended {date}, {mapped} articles, joined {joined}/{known} current")
    con.execute("DROP TABLE IF EXISTS article_en_fts")
    con.execute("CREATE VIRTUAL TABLE article_en_fts USING fts5(text, content='article_en', tokenize='porter unicode61')")
    con.execute("INSERT INTO article_en_fts(article_en_fts) VALUES('rebuild')")
    con.commit()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
