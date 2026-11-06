"""Which health/medical acts are in ChronoMed-TW, and how they map between sources (same method as src/registry.py).

LY law ids: LYAPI v2 `laws?主管機關=衛生福利部` (all pages, cached in data/med/raw/ly/_laws_mohw.json); an act is
matched only by its EXACT current title. MOJ pcodes: the MOJ search page, exact title only (the regex of
registry.resolve_pcode); search pages are cached in data/med/raw/moj/search/. Nothing is guessed: an act whose title
is not found exactly is reported and left out.

  python -I src/med/registry_med.py resolve      # writes data/med/raw/ly/lyids.json and data/med/raw/moj/pcodes.json
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from medcfg import ACTS, LYIDS, PCODES, RAW_LY, RAW_MOJ, RAW_MOJ_EN, polite_get, write_atomic  # noqa: E402

API = "https://ly.govapi.tw/v2"
EN_TITLES = RAW_MOJ_EN / "english_titles.json"


def ly_catalog() -> list[dict]:
    f = RAW_LY / "_laws_mohw.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    rows, page = [], 1
    while True:
        d = json.loads(polite_get(f"{API}/laws?" + urllib.parse.urlencode({"主管機關": "衛生福利部", "limit": 100, "page": page})))
        rows += d["laws"]
        if page >= d.get("total_page", 1):
            break
        page += 1
    write_atomic(f, json.dumps(rows, ensure_ascii=False, indent=1))
    return rows


def resolve_pcode(title: str) -> str | None:
    """Same rule as registry.resolve_pcode: the MOJ search result whose title is EXACTLY `title`."""
    f = RAW_MOJ / "search" / (title + ".html")
    if not f.exists():
        url = "https://law.moj.gov.tw/Law/LawSearchResult.aspx?ty=ONEBAR&kw=" + urllib.parse.quote(title)
        write_atomic(f, polite_get(url))
    page = f.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r'title="([^"]+)" href="[^"]*pcode=([A-Z0-9]+)', page):
        if m.group(1) == title:  # exact title only; never guess
            return m.group(2)
    return None


def lyids() -> dict[str, str]:
    """title -> LY law id"""
    return json.loads(LYIDS.read_text(encoding="utf-8")) if LYIDS.exists() else {}


def pcodes() -> dict[str, str]:
    """LY law id -> MOJ pcode"""
    return json.loads(PCODES.read_text(encoding="utf-8")) if PCODES.exists() else {}


def english_titles() -> dict[str, str]:
    return json.loads(EN_TITLES.read_text(encoding="utf-8")) if EN_TITLES.exists() else {}


def laws() -> dict[str, tuple[str, str]]:
    """LY law id -> (Chinese title, official English title or ''), in ACTS order; only fully resolved acts."""
    ids, codes, en = lyids(), pcodes(), english_titles()
    return {ids[t]: (t, en.get(ids[t], "")) for t in ACTS if ids.get(t) and codes.get(ids[t])}


def resolve() -> None:
    cat = ly_catalog()
    ids, codes = lyids(), pcodes()
    for title in ACTS:
        if not ids.get(title):
            hits = [r for r in cat if r.get("名稱") == title]
            ids[title] = hits[0]["法律編號"] if len(hits) == 1 else None
            write_atomic(LYIDS, json.dumps(ids, ensure_ascii=False, indent=1))
        lid = ids[title]
        if lid and not codes.get(lid):
            codes[lid] = resolve_pcode(title)
            write_atomic(PCODES, json.dumps(codes, ensure_ascii=False, indent=1))
        print(title, lid, lid and codes.get(lid))


if __name__ == "__main__" and sys.argv[1:] == ["resolve"]:
    sys.stdout.reconfigure(encoding="utf-8")
    resolve()
