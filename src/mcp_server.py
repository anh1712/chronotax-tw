"""MCP server: lets any MCP client (Claude, ChatGPT, agents) query Taiwan tax law by date.

  .venv/Scripts/python src/mcp_server.py            # stdio (add to a client's MCP config)
  .venv/Scripts/python src/mcp_server.py http       # streamable HTTP

Tools are read-only and deterministic (no LLM inside):
  get_article(law_id, article, as_of, known_on?)   text in force on as_of; with known_on, only what was published by then
  article_history(law_id, article)                 every version with validity interval and date basis
  search_law(text, as_of, law_id?)                 full-text search restricted to the law in force on as_of
  find_sources(question)                           period resolution + retrieval used by the QA layer
  verify_claim(claim, law_id, article, as_of)      are the amounts/percentages in a claim stated in that version?
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402

DB = Path(__file__).resolve().parent.parent / "data" / "lawtw.db"
mcp = MCPServer("chronotax-tw", instructions=(
    "Point-in-time Taiwan tax law (23 acts, every version since enactment). Always pass the date the user's question "
    "is about (as_of, YYYY-MM-DD; for income tax use Jan 1 of the tax year). Cite law_id + article + validity interval."))


def _q(sql, params=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def _slim(r: dict) -> dict:
    keep = ("law_id", "article_no", "valid_from", "valid_to", "published", "retro", "deleted", "from_basis",
            "first_ly_version", "text")
    return {k: r[k] for k in keep if k in r}


@mcp.tool()
def list_laws() -> list[dict]:
    """The acts in the store with their ids (law_id) and English names."""
    return _q("SELECT law_id, name, name_en, pcode FROM law ORDER BY law_id")


@mcp.tool()
def get_article(law_id: str, article: str, as_of: str, known_on: str | None = None) -> dict:
    """Article text in force on `as_of` (article like 第十七條 or 第十七條之一). With `known_on`, returns the version a
    reader could have known on that day (retroactive amendments published later are excluded)."""
    if known_on:
        rows = _q("SELECT * FROM article_version WHERE law_id=? AND article_no=? AND published<=? AND valid_from<=? "
                  "ORDER BY valid_from DESC, published DESC LIMIT 1", (law_id, article, known_on, as_of))
    else:
        rows = _q("SELECT * FROM article_version WHERE law_id=? AND article_no=? AND valid_from<=? "
                  "AND (valid_to IS NULL OR valid_to>?)", (law_id, article, as_of, as_of))
    if not rows:
        return {"found": False}
    en = _q("SELECT label, text, en_amended FROM article_en WHERE law_id=? AND article_no=?", (law_id, article))
    return {"found": True, **_slim(rows[0]), "english_current": en[0] if en else None}


@mcp.tool()
def article_history(law_id: str, article: str) -> list[dict]:
    """Every version of one article: validity interval, publication date, date basis, retroactive flag."""
    return [{k: v for k, v in _slim(r).items() if k != "text"} | {"chars": len(r["text"])}
            for r in _q("SELECT * FROM article_version WHERE law_id=? AND article_no=? ORDER BY valid_from, published",
                        (law_id, article))]


@mcp.tool()
def search_law(text: str, as_of: str, law_id: str | None = None, k: int = 8) -> list[dict]:
    """Full-text search (≥3 characters, Chinese) over articles in force on `as_of`."""
    sql = ("SELECT av.* FROM article_fts f JOIN article_version av ON av.id=f.rowid WHERE article_fts MATCH ? "
           "AND av.deleted=0 AND av.valid_from<=? AND (av.valid_to IS NULL OR av.valid_to>?)"
           + (" AND av.law_id=?" if law_id else "") + " ORDER BY bm25(article_fts) LIMIT ?")
    params = ['"' + text.replace('"', "") + '"', as_of, as_of] + ([law_id] if law_id else []) + [k]
    return [_slim(r) for r in _q(sql, params)]


@mcp.tool()
def find_sources(question: str, law_id: str | None = None) -> dict:
    """Resolve the period a question is about (ROC/Gregorian years, tax years) and return the article versions in
    force for it, best first. Works for Chinese or English questions."""
    period = answer.resolve_period(question)
    hits = answer.retrieve(question, period["as_of"], law_id)
    return {"period": period, "sources": [_slim(h) | {"law": h["law_name"]} for h in hits]}


@mcp.tool()
def verify_claim(claim: str, law_id: str, article: str, as_of: str) -> dict:
    """Check that every amount / percentage in `claim` is stated in the article version in force on `as_of`."""
    art = get_article(law_id, article, as_of)
    if not art.get("found"):
        return {"verified": False, "problems": ["article not in force on that date"]}
    c = answer.verify([{"text": claim, "cite": ["S1"]}], {"S1": art})[0]
    return {"verified": c["verified"], "problems": c["problems"], "version": {k: art[k] for k in ("valid_from", "valid_to")}}


if __name__ == "__main__":
    mcp.run("streamable-http" if sys.argv[1:] == ["http"] else "stdio")
