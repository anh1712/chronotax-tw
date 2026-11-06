"""Build data/lawtw.db: point-in-time article versions for Taiwan tax laws.

Pipeline (cheap, 0 token, re-runnable):
  LYAPI full-text versions (fetch_ly.py)  +  MOJ history (promulgation/effective dates)
  → version table (LY passage date ↔ MOJ promulgation ↔ effective date, with the rule that produced it)
  → article_version intervals [valid_from, valid_to) keyed by effective dates
  → FTS5 (trigram tokenizer: works for Chinese without a word segmenter)
Design rule: effective dates come from RULES with a recorded
basis; unmatched/uncertain data is flagged, never guessed; measure the store before evaluating.
Per-article date, in this order (date audit, docs/AUDIT_DATES.md): an article named by the MOJ history entry or an
Executive Yuan order printed in it (table history_rule) > the act's own commencement article (effect_rules) > not in
force yet (pending=1: a new article of an amendment delegated to the Executive Yuan that no order names, or an article
the entry says is delegated with no order) > the amendment's main date. Pending rows are zero-length at 9999-12-31;
the text before them stays in force.
"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import effect_rules  # noqa: E402
import moj_history  # noqa: E402
from registry import LAWS, pcodes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "ly"
DB = ROOT / "data" / "lawtw.db"


SCHEMA = """
CREATE TABLE law(law_id TEXT PRIMARY KEY, name TEXT, name_en TEXT, pcode TEXT);
CREATE TABLE version(
  law_id TEXT, ly_version TEXT, ly_date TEXT, action TEXT,
  moj_no INTEGER, promulgated TEXT, effective TEXT, effective_basis TEXT, moj_note TEXT,
  PRIMARY KEY(law_id, ly_version));
CREATE TABLE article_version(
  id INTEGER PRIMARY KEY, law_id TEXT, article_no TEXT, seq INTEGER, chapter TEXT, text TEXT,
  first_ly_version TEXT, valid_from TEXT, valid_to TEXT, from_basis TEXT,
  published TEXT, retro INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0, overtaken INTEGER DEFAULT 0,
  pending INTEGER DEFAULT 0);
CREATE TABLE commencement_rule(law_id TEXT, amend_date TEXT, articles TEXT, effective TEXT, basis TEXT);
CREATE TABLE history_rule(law_id TEXT, ly_version TEXT, moj_no INTEGER, article_no TEXT, effective TEXT, basis TEXT,
  kind TEXT);  -- kind: article (dated by the MOJ history entry) | partial (paragraph-level, not applied) | conflict
CREATE INDEX ix_av ON article_version(law_id, article_no, valid_from);
CREATE VIRTUAL TABLE article_fts USING fts5(text, content='article_version', content_rowid='id', tokenize='trigram');
"""


def match_versions(ly_versions: list[dict], moj: list[dict]) -> list[dict]:
    """Pair each LY version (passage date) with the first MOJ entry promulgated on/after it, within 120 days."""
    rows, j = [], 0
    for v in sorted(ly_versions, key=lambda x: x["日期"]):
        ly_date = dt.date.fromisoformat(v["日期"])
        hit = None
        while j < len(moj):
            p = dt.date.fromisoformat(moj[j]["promulgated"])
            if p < ly_date:
                j += 1
                continue
            if (p - ly_date).days <= 120:
                hit = moj[j]
                j += 1
            break
        rows.append((v, hit))
    return rows


PENDING_DATE = "9999-12-31"  # not in force yet (delegated to the Executive Yuan, no order): zero-length, pending=1


def _art_num(key: str) -> tuple[int, int]:
    """'第十七條之四' -> (17, 4)."""
    import re
    m = re.fullmatch(r"第([〇零一二三四五六七八九十百]+)條(?:之([〇零一二三四五六七八九十百]+))?", key)
    return (moj_history.cn_num(m.group(1)), moj_history.cn_num(m.group(2)) if m.group(2) else 0) if m else (-1, -1)


def _expand(ref: str, keys: list[str]) -> list[str]:
    """MOJ history reference ('5-1', range '4~7') -> LY article keys present in this version. A range includes the
    之-articles between its ends (第4～7條 covers 第六條之一)."""
    def num(r):
        a, _, b = r.partition("-")
        return int(a), int(b or 0)
    lo, _, hi = ref.partition("~")
    lo, hi = num(lo), num(hi or lo)
    return [k for k in keys if lo <= _art_num(k) <= hi]


def build() -> None:
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    report = []
    codes = pcodes()
    for law_id, (_, name_en) in LAWS.items():
        pcode = codes.get(law_id)
        if not pcode or not (RAW / law_id / "_law.json").exists():
            report.append(f"{law_id}: skipped (pcode={pcode}, fetched={(RAW / law_id).exists()})")
            continue
        meta = json.loads((RAW / law_id / "_law.json").read_text(encoding="utf-8"))
        name = meta["law"].get("data", meta["law"]).get("名稱") if isinstance(meta["law"], dict) else law_id
        con.execute("INSERT INTO law VALUES(?,?,?,?)", (law_id, name, name_en, pcode))
        moj = moj_history.parse(moj_history.fetch(pcode))
        pairs = match_versions(meta["versions"], moj)
        unmatched = 0
        timeline = []  # (ly_version, effective, basis, rows, dates, published, history rules, delegated)
        for v, m in pairs:
            vid = v["版本編號"]
            if m is None:
                unmatched += 1
                eff, basis = v["日期"], "ly_date_fallback"  # flagged: no MOJ entry found
            else:
                eff, basis = m["effective"], m["effective_basis"]
                if eff is None:  # 施行日期由行政院定之 with no date in the entry
                    eff, basis = m["promulgated"], "unknown_using_promulgation"
            con.execute("INSERT INTO version VALUES(?,?,?,?,?,?,?,?,?)", (
                law_id, vid, v["日期"], v["動作"], m and m["no"], m and m["promulgated"], eff, basis, m and m["note"]))
            rows = json.loads((RAW / law_id / (vid.split(":", 1)[1] + ".json")).read_text(encoding="utf-8"))
            dates = {v["日期"]} | ({m["promulgated"]} if m else set())
            # per-article dates named by the MOJ history entry (and the Executive Yuan orders printed in it)
            keys = [r.get("條號") for r in rows if (r.get("條號") or "").startswith("第")]
            hist = {}
            for kind, lst in (("article", (m or {}).get("rules", [])), ("partial", [
                    {"ref": ref, "effective": p["effective"], "basis": p["basis"]}
                    for p in (m or {}).get("partial", []) for ref in p["refs"]])):
                for r in lst:
                    for art in _expand(r["ref"], keys):
                        con.execute("INSERT INTO history_rule VALUES(?,?,?,?,?,?,?)",
                                    (law_id, vid, m["no"], art, r["effective"], r["basis"], kind))
                        if kind == "article":
                            hist[art] = (PENDING_DATE, "pending_executive_yuan") if r["effective"] == moj_history.PENDING \
                                else (r["effective"], "article_" + r["basis"])
            timeline.append((vid, eff, basis, rows, dates, (m and m["promulgated"]) or v["日期"], hist,
                             bool(m and m.get("rest_undated"))))

        # per-article commencement rules, from the latest version's commencement article (cumulative in TW acts)
        comm = effect_rules.find_commencement(timeline[-1][3]) if timeline else None
        parsed = effect_rules.parse(comm) if comm else {"rules": [], "unparsed": []}
        for r in parsed["rules"]:
            con.execute("INSERT INTO commencement_rule VALUES(?,?,?,?,?)",
                        (law_id, r["amend_date"], json.dumps(r["articles"], ensure_ascii=False), r["effective"], r["basis"]))

        def eff_for(art, dates, v_eff, v_basis, hist=None, new=False, delegated=False):
            """Order: article named by the MOJ history entry > the act's commencement article (article, then whole
            amendment) > not in force yet (a NEW article of a delegated amendment that no order names) > the
            amendment's main date. History vs commencement-article disagreements are recorded, history wins."""
            hit = effect_rules.lookup(parsed["rules"], dates, art)
            if hist and art in hist:
                if hit and hit[0] and hit[0] != hist[art][0]:
                    con.execute("INSERT INTO history_rule VALUES(?,?,?,?,?,?,?)",
                                (law_id, None, None, art, f"{hist[art][0]} vs {hit[0]}", f"{hist[art][1]} vs {hit[1]}",
                                 "conflict"))
                return hist[art]
            if hit and hit[0]:
                return hit
            if delegated and new:
                return PENDING_DATE, "pending_executive_yuan"
            return v_eff, v_basis

        # article intervals: an article's text is valid from the effective date of the version where it first
        # appears with that text, until the effective date of the next version where it differs or disappears.
        open_: dict[str, dict] = {}
        n_av = 0
        n_rule = 0
        for vid, v_eff, v_basis, rows, dates, published, hist, delegated in timeline:
            seen, chapter = set(), None
            for r in rows:
                if r.get("章名"):
                    chapter = r["章名"].strip()
                art, text = r.get("條號"), (r.get("內容") or "").strip()
                if not art or art == "法律名稱" or not text:
                    continue
                seen.add(art)
                cur = open_.get(art)
                if cur and cur["text"] == text:
                    continue
                eff, basis = eff_for(art, dates, v_eff, v_basis, hist, new=cur is None, delegated=delegated)
                n_rule += basis.startswith("commencement")
                if cur:
                    cur["valid_to"] = eff
                open_[art] = {"art": art, "seq": int(r.get("順序") or 0), "chapter": chapter, "text": text,
                              "first": vid, "valid_from": eff, "valid_to": None, "basis": basis,
                              "published": published, "retro": int(eff < published), "pending": int(eff == PENDING_DATE)}
                cur and _insert(con, law_id, cur)
                n_av += bool(cur)
            for art in [a for a in open_ if a not in seen]:  # deleted in this version: close + tombstone row
                eff, basis = eff_for(art, dates, v_eff, v_basis, hist)
                gone = open_.pop(art)
                gone["valid_to"] = eff
                _insert(con, law_id, gone)
                _insert(con, law_id, {**gone, "text": "", "first": vid, "valid_from": eff, "valid_to": None,
                                      "basis": basis, "published": published, "retro": 0, "deleted": 1, "pending": 0})
                n_av += 1
        for cur in open_.values():
            _insert(con, law_id, cur)
            n_av += 1
        bases = con.execute("SELECT effective_basis, count(*) FROM version WHERE law_id=? GROUP BY 1", (law_id,)).fetchall()
        report.append(f"{law_id} {name}: {len(pairs)} LY versions, MOJ entries {len(moj)}, unmatched {unmatched}, "
                      f"article_versions {n_av}, per-article commencement {n_rule}, rules {len(parsed['rules'])}"
                      f" (unparsed {len(parsed['unparsed'])}), version basis {dict(bases)}")
    report.append(f"interval conflicts resolved by effective-date order: {reorder_intervals(con)}")
    con.execute("INSERT INTO article_fts(article_fts) VALUES('rebuild')")
    con.commit()
    print("\n".join(report))


def reorder_intervals(con) -> int:
    """Valid-time intervals must follow EFFECTIVE order, not passage order: a later amendment can take effect before an
    earlier pending one (所得稅法 2011-01 amendment effective 2012-01-01 vs 2011-10 amendment effective 2011-11-11),
    and retroactive amendments start before they were published. Sort each article's versions by
    (valid_from, published) and let each run until the next one starts; ties keep the later-published text.
    A pending version is OVERTAKEN when a later-published version takes effect on or before its start: the later
    full text already contains it (所得稅法 2011-01 amendment, effective 2012-01-01, was overtaken by the 2011-10
    amendment effective 2011-11-11). Overtaken versions get a zero-length interval; the bitemporal `known` lookup
    still finds them for knowledge dates before the overtaking version was published.
    PENDING versions (施行日期由行政院定之, no order yet) never apply: zero-length at PENDING_DATE, and the text before
    them stays in force."""
    changed = 0
    con.execute("UPDATE article_version SET valid_to=valid_from WHERE pending=1")
    keys = con.execute("SELECT DISTINCT law_id, article_no FROM article_version").fetchall()
    for law_id, art in keys:
        rows = con.execute("SELECT id, valid_from, valid_to, published FROM article_version WHERE law_id=? "
                           "AND article_no=? AND pending=0 ORDER BY valid_from, published, id", (law_id, art)).fetchall()
        live = [r for r in rows if not any(o[3] > r[3] and o[1] <= r[1] for o in rows if o[0] != r[0])]
        for r in rows:
            if r not in live:
                con.execute("UPDATE article_version SET valid_to=valid_from, overtaken=1 WHERE id=?", (r[0],))
                changed += r[2] != r[1]
        for i, (rid, vf, vt, _) in enumerate(live):
            nxt = live[i + 1][1] if i + 1 < len(live) else None
            if nxt != vt:
                con.execute("UPDATE article_version SET valid_to=? WHERE id=?", (nxt, rid))
                changed += 1
    return changed


def _insert(con, law_id, a):
    if a["valid_to"] is not None and a["valid_to"] < a["valid_from"]:
        a["valid_to"] = a["valid_from"]  # superseded retroactively before it ever applied: zero-length interval
    con.execute(
        "INSERT INTO article_version(law_id,article_no,seq,chapter,text,first_ly_version,valid_from,valid_to,from_basis,"
        "published,retro,deleted,pending) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (law_id, a["art"], a["seq"], a["chapter"], a["text"], a["first"], a["valid_from"], a["valid_to"], a["basis"],
         a.get("published"), a.get("retro", 0), a.get("deleted", 0), a.get("pending", 0)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build()
