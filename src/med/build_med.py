"""Build data/med/medtw.db: the ChronoTax point-in-time store for 20 Taiwan health/medical acts.

  python -I src/med/build_med.py               # ChronoMed store (extended commencement rules) -> data/med/medtw.db
  python -I src/med/build_med.py --tax-parser  # the ORIGINAL build_db.build(), run unchanged on the same medical data
                                               # -> data/med/medtw_taxparser.db (what the tax-law rules would give)

The extended build is a copy of build_db.build() (same version matching, same interval logic, same FTS index; the
schema, match_versions, reorder_intervals and effect_rules are imported from the original files, not copied).
Changes are marked MED-1 … MED-6 in the code:
  MED-1 paths/acts: data/med/raw/ly, data/med/medtw.db; acts from registry_med.
  MED-2 MOJ history parsed by moj_med.parse (relative dates, 除…外 exceptions, Executive Yuan orders, chapters).
  MED-3 per-article dates: (a) articles/chapters named in the MOJ entry or its Executive Yuan orders, then (b) the act's
        own commencement article (effect_rules.lookup, unchanged), then (c) the amendment-level date. Disagreements
        between (a) and (b) are logged in table rule_conflict.
  MED-4 an article whose date the Executive Yuan has not set is NOT put in force (table pending_article). In a full-text
        revision the old text still ends on the revision's date (a gap row, deleted=1, from_basis=pending_executive_yuan).
  MED-5 paragraph-level exceptions (第4條第1項第4款 …) are kept in table partial_commencement; the article keeps the main
        date and its version row is flagged 'partial'.
  MED-6 an MOJ entry with no LY version of its own (LYAPI merged two amendments passed the same day) gives its own date to
        the articles it names, inside the LY version matched just before it (≤ 30 days).
"""
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402  (paths, sys.path, dont_write_bytecode)
from medcfg import DB, MED, RAW_LY, RESULTS, write_atomic  # noqa: E402
import build_db  # noqa: E402  original
import effect_rules  # noqa: E402  original
import moj_history  # noqa: E402  original
import moj_med  # noqa: E402
import registry_med  # noqa: E402
from build_db import SCHEMA, match_versions, reorder_intervals  # noqa: E402  original
from moj_med import PENDING  # noqa: E402

TAXPARSER_DB = MED / "medtw_taxparser.db"
EXTRA = """
ALTER TABLE article_version ADD COLUMN flag TEXT;
CREATE TABLE history_rule(law_id TEXT, moj_no INTEGER, promulgated TEXT, articles TEXT, chapters TEXT, effective TEXT,
  basis TEXT, source TEXT);
CREATE TABLE partial_commencement(law_id TEXT, moj_no INTEGER, promulgated TEXT, article_no TEXT, effective TEXT,
  basis TEXT, ref TEXT);
CREATE TABLE pending_article(law_id TEXT, article_no TEXT, ly_version TEXT, promulgated TEXT, full_text_revision INTEGER,
  text TEXT);
CREATE TABLE rule_conflict(law_id TEXT, article_no TEXT, ly_version TEXT, history_eff TEXT, article_rule_eff TEXT);
CREATE TABLE build_report(law_id TEXT, name TEXT, report TEXT);
"""
CHAP_RX = re.compile(r"^第[〇一二三四五六七八九十百]+章(?:之[〇一二三四五六七八九十]+)?")


def _ins(con, law_id, a):
    """build_db._insert + the flag column."""
    if a["valid_to"] is not None and a["valid_to"] < a["valid_from"]:
        a["valid_to"] = a["valid_from"]  # superseded retroactively before it ever applied: zero-length interval
    con.execute(
        "INSERT INTO article_version(law_id,article_no,seq,chapter,text,first_ly_version,valid_from,valid_to,from_basis,"
        "published,retro,deleted,flag) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (law_id, a["art"], a["seq"], a["chapter"], a["text"], a["first"], a["valid_from"], a["valid_to"], a["basis"],
         a.get("published"), a.get("retro", 0), a.get("deleted", 0), a.get("flag")))


def build() -> dict:
    medcfg.patch_pipeline()
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA + EXTRA)
    codes = registry_med.pcodes()
    per_law = {}
    for law_id, (name, name_en) in registry_med.laws().items():  # MED-1
        pcode = codes[law_id]
        meta = json.loads((RAW_LY / law_id / "_law.json").read_text(encoding="utf-8"))
        con.execute("INSERT INTO law VALUES(?,?,?,?)", (law_id, name, name_en, pcode))
        moj = [e for e in moj_med.parse(moj_med.page(pcode)) if e["is_promulgation"]]  # MED-2
        pairs = match_versions(meta["versions"], moj)
        used = {m["no"] for _, m in pairs if m}
        # MED-6: MOJ entries without an LY version of their own
        extra = {}
        for e in moj:
            if e["no"] in used:
                continue
            prev = [(v, m) for v, m in pairs if m and m["promulgated"] <= e["promulgated"] and
                    (dt.date.fromisoformat(e["promulgated"]) - dt.date.fromisoformat(m["promulgated"])).days <= 30]
            if prev:
                arts = [moj_med._cn_art(a) for a in e["articles"] if re.fullmatch(r"\d+(?:-\d+)?", a)]
                extra[prev[-1][0]["版本編號"]] = (e, arts)
        for e in moj:
            for r in e["rules"] + e["pending_refs"]:
                con.execute("INSERT INTO history_rule VALUES(?,?,?,?,?,?,?,?)", (
                    law_id, e["no"], e["promulgated"], json.dumps(r["articles"], ensure_ascii=False),
                    json.dumps(r["chapters"], ensure_ascii=False), None if r["effective"] == PENDING else r["effective"],
                    r["basis"], r.get("source")))
            for p in e["partial"]:
                for a in p["articles"]:
                    con.execute("INSERT INTO partial_commencement VALUES(?,?,?,?,?,?,?)", (
                        law_id, e["no"], e["promulgated"], a, None if p["effective"] == PENDING else p["effective"],
                        p["basis"], p["ref"]))
        unmatched = 0
        timeline = []
        for v, m in pairs:
            vid = v["版本編號"]
            if m is None:
                unmatched += 1
                eff, basis = v["日期"], "ly_date_fallback"  # flagged: no MOJ entry found
            else:
                eff, basis = m["effective"], m["effective_basis"]
                if eff is None:  # MED-4 (the original used the promulgation date: 'unknown_using_promulgation')
                    eff = PENDING
            con.execute("INSERT INTO version VALUES(?,?,?,?,?,?,?,?,?)", (
                law_id, vid, v["日期"], v["動作"], m and m["no"], m and m["promulgated"], None if eff == PENDING else eff,
                basis, m and m["note"]))
            rows = json.loads((RAW_LY / law_id / (vid.split(":", 1)[1] + ".json")).read_text(encoding="utf-8"))
            dates = {v["日期"]} | ({m["promulgated"]} if m else set())
            full_rev = "全文" in (v["動作"] or "") or bool(m and m["whole_text"])
            timeline.append((vid, eff, basis, rows, dates, (m and m["promulgated"]) or v["日期"], m, full_rev))

        # per-article commencement rules from the latest version's commencement article (original effect_rules)
        comm = effect_rules.find_commencement(timeline[-1][3]) if timeline else None
        parsed = effect_rules.parse(comm) if comm else {"rules": [], "unparsed": []}
        for r in parsed["rules"]:
            con.execute("INSERT INTO commencement_rule VALUES(?,?,?,?,?)",
                        (law_id, r["amend_date"], json.dumps(r["articles"], ensure_ascii=False), r["effective"], r["basis"]))

        def eff_for(art, chap, dates, v_eff, v_basis, m, vid):  # MED-3
            if vid in extra and art in extra[vid][1]:  # MED-6
                return extra[vid][0]["effective"], "moj_entry_without_ly_version"
            hist = None
            if m:
                for r in m["rules"]:
                    if art in r["articles"] or (chap and chap in r["chapters"]):
                        hist = (r["effective"], "history_" + r["basis"])
                        break
                if hist is None:
                    for r in m["pending_refs"]:
                        if art in r["articles"] or (chap and chap in r["chapters"]):
                            hist = (PENDING, "pending_executive_yuan")
                            break
            hit = effect_rules.lookup(parsed["rules"], dates, art)  # original
            art_rule = hit if hit and hit[0] else None
            if hist and art_rule and hist[0] != art_rule[0]:
                con.execute("INSERT INTO rule_conflict VALUES(?,?,?,?,?)", (law_id, art, vid, hist[0], art_rule[0]))
            if hist:
                return hist
            if art_rule:
                return art_rule
            return v_eff, v_basis

        open_: dict[str, dict] = {}
        pending_text: dict[str, str] = {}
        n_av = n_rule = n_pending = 0
        for vid, v_eff, v_basis, rows, dates, published, m, full_rev in timeline:
            seen, chapter, top = set(), None, None
            for r in rows:
                if r.get("章名"):
                    chapter = r["章名"].strip()
                    cm = CHAP_RX.match(re.sub(r"\s+", "", chapter))
                    if cm:
                        top = cm.group(0)
                art, text = r.get("條號"), (r.get("內容") or "").strip()
                if not art or art == "法律名稱" or not text:
                    continue
                seen.add(art)
                cur = open_.get(art)
                if cur and cur["text"] == text:
                    continue
                if pending_text.get(art) == text:
                    continue  # MED-4: same text, still waiting for its commencement date
                eff, basis = eff_for(art, top, dates, v_eff, v_basis, m, vid)
                if eff == PENDING:  # MED-4
                    pending_text[art] = text
                    n_pending += 1
                    con.execute("INSERT INTO pending_article VALUES(?,?,?,?,?,?)",
                                (law_id, art, vid, published, int(full_rev), text))
                    if full_rev and cur and v_eff != PENDING:
                        gone = open_.pop(art)
                        gone["valid_to"] = v_eff
                        _ins(con, law_id, gone)
                        _ins(con, law_id, {**gone, "text": "", "first": vid, "valid_from": v_eff, "valid_to": None,
                                           "basis": "pending_executive_yuan", "published": published, "retro": 0,
                                           "deleted": 1, "flag": "pending_gap"})
                        n_av += 1
                    continue
                pending_text.pop(art, None)
                n_rule += basis.startswith(("commencement", "history", "moj_entry"))
                if cur:
                    cur["valid_to"] = eff
                open_[art] = {"art": art, "seq": int(r.get("順序") or 0), "chapter": chapter, "text": text,
                              "first": vid, "valid_from": eff, "valid_to": None, "basis": basis,
                              "published": published, "retro": int(eff < published)}
                cur and _ins(con, law_id, cur)
                n_av += bool(cur)
            for art in [a for a in open_ if a not in seen]:  # deleted in this version: close + tombstone row
                eff, basis = eff_for(art, None, dates, v_eff, v_basis, m, vid)
                if eff == PENDING:
                    continue  # repeal not in force yet: keep the text
                gone = open_.pop(art)
                gone["valid_to"] = eff
                _ins(con, law_id, gone)
                _ins(con, law_id, {**gone, "text": "", "first": vid, "valid_from": eff, "valid_to": None,
                                   "basis": basis, "published": published, "retro": 0, "deleted": 1})
                n_av += 1
        for cur in open_.values():
            _ins(con, law_id, cur)
            n_av += 1
        bases = dict(con.execute("SELECT effective_basis, count(*) FROM version WHERE law_id=? GROUP BY 1", (law_id,)))
        per_law[law_id] = {
            "name": name, "name_en": name_en, "ly_versions": len(pairs), "moj_entries": len(moj),
            "unmatched_ly": unmatched, "moj_without_ly": sorted(e["no"] for e in moj if e["no"] not in used),
            "article_versions_built": n_av, "per_article_dates_applied": n_rule, "pending_articles": n_pending,
            "commencement_article_rules": len(parsed["rules"]), "commencement_article_unparsed": parsed["unparsed"],
            "version_basis": bases}
        con.execute("INSERT INTO build_report VALUES(?,?,?)", (law_id, name, json.dumps(per_law[law_id], ensure_ascii=False)))
    changed = reorder_intervals(con)  # original: effective-date order, overtaken pending amendments
    # MED-5: flag article versions that started with a paragraph-level exception in their amendment
    con.execute("""UPDATE article_version SET flag = coalesce(flag || ',', '') || 'partial' WHERE id IN (
        SELECT av.id FROM article_version av JOIN version v ON v.law_id=av.law_id AND v.ly_version=av.first_ly_version
        JOIN partial_commencement p ON p.law_id=av.law_id AND p.article_no=av.article_no AND p.moj_no=v.moj_no)""")
    con.execute("INSERT INTO article_fts(article_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    return {"per_law": per_law, "interval_changes_by_reorder": changed}


def build_with_tax_parser() -> None:
    """The original pipeline, unchanged (build_db.build, moj_history.parse, effect_rules), on the medical data."""
    medcfg.patch_pipeline()
    build_db.DB = TAXPARSER_DB
    build_db.build()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--tax-parser" in sys.argv:
        build_with_tax_parser()
    else:
        rep = build()
        RESULTS.mkdir(parents=True, exist_ok=True)
        write_atomic(RESULTS / "build_report.json", json.dumps(rep, ensure_ascii=False, indent=1))
        for lid, r in rep["per_law"].items():
            print(lid, r["name"], {k: r[k] for k in ("ly_versions", "moj_entries", "unmatched_ly", "moj_without_ly",
                                                     "article_versions_built", "per_article_dates_applied",
                                                     "pending_articles")})
        print("interval changes by reorder_intervals:", rep["interval_changes_by_reorder"])
