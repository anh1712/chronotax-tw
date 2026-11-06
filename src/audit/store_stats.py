"""Store-level counts that README/REPORT publish, for the current store and the corrected store (same SQL).

  python -I -B src/audit/store_stats.py   -> data/audit/out/store_stats.json (+ console)

Tax acts only (law_id not 'G…'). article version = row with deleted=0 (README "3,555"). retroactive = retro=1
(README "54"). overtaken = overtaken=1 (README "4"). Overlap check: two non-empty in-force intervals of the same
article that intersect (REPORT "0 overlapping non-empty intervals").
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CUR_DB, FIXED_DB, OUT, TAG, ro, write_json  # noqa: E402


def stats(path: Path) -> dict:
    c = ro(path)
    one = lambda q: c.execute(q).fetchone()[0]  # noqa: E731
    cols = [r[1] for r in c.execute("PRAGMA table_info(article_version)")]
    pend = "pending=1" if "pending" in cols else "0"
    W = "law_id NOT LIKE 'G%'"
    out = {
        "acts": one(f"SELECT count(*) FROM law WHERE {W}"),
        "versions": one(f"SELECT count(*) FROM version WHERE {W}"),
        "article_versions": one(f"SELECT count(*) FROM article_version WHERE {W} AND deleted=0"),
        "articles": one(f"SELECT count(DISTINCT law_id||article_no) FROM article_version WHERE {W}"),
        "retroactive_article_versions": one(f"SELECT count(*) FROM article_version WHERE {W} AND deleted=0 AND retro=1"),
        "retroactive_versions": one(f"SELECT count(*) FROM version WHERE {W} AND effective < promulgated"),
        "overtaken_article_versions": one(f"SELECT count(*) FROM article_version WHERE {W} AND overtaken=1"),
        "pending_article_versions": one(f"SELECT count(*) FROM article_version WHERE {W} AND {pend}"),
        "zero_length_non_deleted": one(f"SELECT count(*) FROM article_version WHERE {W} AND deleted=0 AND valid_to=valid_from"),
        "version_basis": dict(c.execute(f"SELECT effective_basis, count(*) FROM version WHERE {W} GROUP BY 1").fetchall()),
        "article_basis": dict(c.execute(f"SELECT from_basis, count(*) FROM article_version WHERE {W} AND deleted=0 "
                                        "GROUP BY 1").fetchall()),
        "versions_delayed_beyond_default": one(f"SELECT count(*) FROM version WHERE {W} AND effective > "
                                               "date(promulgated, '+2 days')"),
    }
    overl = c.execute(
        f"SELECT count(*) FROM article_version a JOIN article_version b ON a.law_id=b.law_id AND a.article_no=b.article_no "
        f"AND a.id<b.id WHERE a.{W.replace('law_id', 'law_id')} AND a.valid_to IS NOT a.valid_from AND b.valid_to IS NOT b.valid_from "
        "AND a.valid_from < coalesce(b.valid_to,'9999-99') AND b.valid_from < coalesce(a.valid_to,'9999-99')").fetchone()[0]
    out["overlapping_non_empty_interval_pairs"] = overl
    out["retroactive_article_version_ids"] = [r[0] for r in c.execute(
        f"SELECT id FROM article_version WHERE {W} AND deleted=0 AND retro=1 ORDER BY id")]
    out["overtaken_ids"] = [r[0] for r in c.execute(f"SELECT id FROM article_version WHERE {W} AND overtaken=1 ORDER BY id")]
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    res = {"current": stats(CUR_DB), "fixed": stats(FIXED_DB)}
    a, b = res["current"], res["fixed"]
    res["retro_only_current"] = sorted(set(a["retroactive_article_version_ids"]) - set(b["retroactive_article_version_ids"]))
    res["retro_only_fixed"] = sorted(set(b["retroactive_article_version_ids"]) - set(a["retroactive_article_version_ids"]))
    write_json(OUT / f"store_stats{TAG}.json", res)
    for k in a:
        if not k.endswith("_ids"):
            print(f"{k:40s} {a[k]!s:60.60s} | {b[k]!s:.80s}")
    print("retro only in current:", res["retro_only_current"], "only in fixed:", res["retro_only_fixed"])
    print("overtaken ids current", a["overtaken_ids"], "fixed", b["overtaken_ids"])


if __name__ == "__main__":
    main()
