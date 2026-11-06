"""ChronoTax-TW demo API + static UI.   python -I src/app.py  → http://127.0.0.1:8017

Endpoints (read-only over data/lawtw.db):
  GET /api/laws                                   laws with version counts
  GET /api/articles?law=01513                     current articles (with English label)
  GET /api/article?law=&art=&as_of=&known_on=     version in force on as_of (bitemporal if known_on), + English gloss
  GET /api/history?law=&art=                      every version with a character-level diff to the previous one
  GET /api/ask?question=&law=                     period → date-filtered retrieval → cited answer → code verification
  GET /api/find?text=&as_of=&law=                 trigram full-text search restricted to the law in force on as_of
"""
import difflib
import sys
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
DB = ROOT / "data" / "lawtw.db"
WEB = ROOT / "web"
IN_FORCE = "valid_from <= :d AND (valid_to IS NULL OR valid_to > :d)"

app = FastAPI(title="ChronoTax-TW")


def q(sql: str, params=()) -> list[dict]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def _en(law: str, art: str) -> dict | None:
    r = q("SELECT label, text, en_amended FROM article_en WHERE law_id=? AND article_no=?", (law, art))
    return r[0] if r else None


def _diff(a: str, b: str) -> list[list]:
    """[[op, text], ...] with op in {eq, ins, del}; character level (Chinese has no spaces)."""
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(["eq", b[j1:j2]])
        else:
            if i2 > i1:
                out.append(["del", a[i1:i2]])
            if j2 > j1:
                out.append(["ins", b[j1:j2]])
    return out


@app.get("/api/laws")
def laws():
    return q("SELECT l.law_id, l.name, l.name_en, l.pcode, count(DISTINCT v.ly_version) versions, "
             "min(v.ly_date) first, max(v.ly_date) last FROM law l JOIN version v USING(law_id) GROUP BY l.law_id "
             "ORDER BY versions DESC")


def _art_key(no: str):
    """第十七條之一 → (17, 1): numeric order instead of the order articles appear in the source."""
    import re
    from moj_history import cn_num
    m = re.match(r"第(.+?)條(?:之(.+))?", no)
    return (cn_num(m.group(1)), cn_num(m.group(2)) if m.group(2) else 0) if m else (10**6, 0)


@app.get("/api/articles")
def articles(law: str):
    return sorted(q("SELECT a.article_no, a.seq, a.chapter, e.label, "
             "(SELECT count(*) FROM article_version x WHERE x.law_id=a.law_id AND x.article_no=a.article_no "
             " AND x.deleted=0 AND (x.valid_to IS NULL OR x.valid_to>x.valid_from)) n_versions "
             "FROM article_version a LEFT JOIN article_en e ON e.law_id=a.law_id AND e.article_no=a.article_no "
             "WHERE a.law_id=? AND a.valid_to IS NULL AND a.deleted=0 ORDER BY a.seq", (law,)),
                  key=lambda r: _art_key(r["article_no"]))


@app.get("/api/article")
def article(law: str, art: str, as_of: str, known_on: str | None = None):
    if known_on:
        rows = q("SELECT * FROM article_version WHERE law_id=? AND article_no=? AND published<=? AND valid_from<=? "
                 "ORDER BY valid_from DESC, published DESC LIMIT 1", (law, art, known_on, as_of))
    else:
        rows = q(f"SELECT * FROM article_version WHERE law_id=:l AND article_no=:a AND {IN_FORCE}",
                 {"l": law, "a": art, "d": as_of})
    if not rows:
        raise HTTPException(404, "not in force on that date")
    r = rows[0]
    cur = q("SELECT id FROM article_version WHERE law_id=? AND article_no=? AND valid_to IS NULL", (law, art))
    r["is_current"] = bool(cur) and cur[0]["id"] == r["id"]
    r["english"] = _en(law, art)
    r["version_info"] = (q("SELECT ly_date, promulgated, effective, effective_basis FROM version WHERE law_id=? "
                           "AND ly_version=?", (law, r["first_ly_version"])) or [None])[0]
    return r


@app.get("/api/history")
def history(law: str, art: str):
    rows = q("SELECT id, text, valid_from, valid_to, from_basis, first_ly_version, published, retro, deleted, pending "
             "FROM article_version WHERE law_id=? AND article_no=? ORDER BY valid_from, published", (law, art))
    prev = ""
    for r in rows:
        r["zero_length"] = r["valid_to"] is not None and r["valid_to"] <= r["valid_from"]
        r["diff"] = _diff(prev, r["text"]) if prev else [["eq", r["text"]]]
        if not r["zero_length"]:
            prev = r["text"]
    return {"versions": rows, "english": _en(law, art)}


@app.get("/api/find")
def find(text: str, as_of: str, law: str | None = None, k: int = 10):
    if len(text) < 3:
        raise HTTPException(400, "trigram search needs at least 3 characters")
    sql = ("SELECT av.law_id, l.name, av.article_no, av.valid_from, av.valid_to, substr(av.text,1,160) snippet "
           "FROM article_fts f JOIN article_version av ON av.id=f.rowid JOIN law l ON l.law_id=av.law_id "
           "WHERE article_fts MATCH :q AND av.deleted=0 AND av.valid_from <= :d AND (av.valid_to IS NULL OR av.valid_to > :d)"
           + (" AND av.law_id=:l" if law else "") + " ORDER BY bm25(article_fts) LIMIT :k")
    return q(sql, {"q": '"' + text.replace('"', "") + '"', "d": as_of, "l": law, "k": k})


@app.get("/api/recent")
def recent(limit: int = 8):
    """Latest amendments across acts (by promulgation), with how many articles changed."""
    return q("SELECT v.law_id, l.name, l.name_en, v.ly_version, v.promulgated, v.effective, v.effective_basis, "
             "(SELECT count(*) FROM article_version a WHERE a.law_id=v.law_id AND a.first_ly_version=v.ly_version) n_art "
             "FROM version v JOIN law l USING(law_id) WHERE v.effective_basis!='moj_current_only' "
             "ORDER BY v.promulgated DESC LIMIT ?", (limit,))


@app.get("/api/retro")
def retro(limit: int = 6):
    """Retroactive article versions (take effect before they were published), newest first."""
    return q("SELECT a.law_id, l.name, a.article_no, a.valid_from, a.published, e.label FROM article_version a "
             "JOIN law l USING(law_id) LEFT JOIN article_en e ON e.law_id=a.law_id AND e.article_no=a.article_no "
             "WHERE a.retro=1 AND a.deleted=0 ORDER BY a.published DESC LIMIT ?", (limit,))


@app.get("/api/stats")
def stats():
    one = lambda sql: q(sql)[0]["n"]
    return {"laws": one("SELECT count(*) n FROM law"), "versions": one("SELECT count(*) n FROM version"),
            "article_versions": one("SELECT count(*) n FROM article_version WHERE deleted=0"),
            "retro": one("SELECT count(*) n FROM article_version WHERE retro=1"),
            "overtaken": one("SELECT count(*) n FROM article_version WHERE overtaken=1")}


@app.get("/api/ask")
def ask_api(question: str, law: str | None = None):
    import answer
    return answer.ask(question, law)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/web", StaticFiles(directory=WEB), name="web")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8017)
