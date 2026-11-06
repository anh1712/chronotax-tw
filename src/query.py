"""Point-in-time lookups over data/lawtw.db.

  python src/query.py article 01513 第十七條 2022-06-01      # text in force on that date
  python src/query.py history 01513 第十七條                  # all versions of one article
  python src/query.py search 01513 免稅額 2025-01-01          # FTS (trigram) restricted to that date
  python src/query.py known 01513 第十七條 2026-03-01 2026-06-01   # bitemporal: rule for 2026-03-01 as known on 2026-06-01
"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "lawtw.db"
IN_FORCE = "valid_from <= :d AND (valid_to IS NULL OR valid_to > :d)"


def con() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def article(law_id: str, art: str, as_of: str):
    return con().execute(f"SELECT * FROM article_version WHERE law_id=:l AND article_no=:a AND {IN_FORCE}",
                         {"l": law_id, "a": art, "d": as_of}).fetchone()


def known(law_id: str, art: str, valid_on: str, known_on: str):
    """Bitemporal lookup: the text that applies to `valid_on`, using only amendments published by `known_on`.
    A retroactive amendment published after `known_on` is invisible, which is what a taxpayer actually saw."""
    return con().execute(
        "SELECT * FROM article_version WHERE law_id=? AND article_no=? AND published<=? AND valid_from<=? "
        "ORDER BY valid_from DESC, published DESC LIMIT 1", (law_id, art, known_on, valid_on)).fetchone()


def history(law_id: str, art: str):
    return con().execute("SELECT * FROM article_version WHERE law_id=? AND article_no=? ORDER BY valid_from",
                         (law_id, art)).fetchall()


def search(law_id: str, q: str, as_of: str, k: int = 5):
    return con().execute(
        f"SELECT av.* FROM article_fts f JOIN article_version av ON av.id=f.rowid "
        f"WHERE article_fts MATCH :q AND av.law_id=:l AND av.deleted=0 AND {IN_FORCE} ORDER BY bm25(article_fts) LIMIT :k",
        {"q": f'"{q}"', "l": law_id, "d": as_of, "k": k}).fetchall()


def _show(r, n=300):
    if r is None:
        print("(not in force on that date)")
        return
    if r["deleted"]:
        print(f"[{r['article_no']}] repealed from {r['valid_from']} ({r['first_ly_version']})")
        return
    print(f"[{r['article_no']}] {r['valid_from']} → {r['valid_to'] or 'now'}  ({r['from_basis']}, {r['first_ly_version']},"
          f" published {r['published']}{', RETROACTIVE' if r['retro'] else ''})")
    print(r["text"][:n].replace("\n", " "), "…" if len(r["text"]) > n else "")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd, *a = sys.argv[1:]
    if cmd == "article":
        _show(article(*a))
    elif cmd == "known":
        _show(known(*a))
    elif cmd == "history":
        for r in history(*a):
            _show(r, 160)
    elif cmd == "search":
        for r in search(*a):
            _show(r, 160)
