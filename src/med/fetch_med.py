"""Download everything ChronoMed-TW needs, politely (<= 1 request/second, cached, resumable).

  python -I src/med/fetch_med.py            # all steps
  python -I src/med/fetch_med.py ly         # only LYAPI versions

Steps (each skips files already on disk, so an interrupted run resumes where it stopped):
  ly       LYAPI v2: law meta + version list + full text of every version -> data/med/raw/ly/<law_id>/<version>.json
           (same calls and file layout as src/fetch_ly.py; only the rate limit and atomic writes differ)
  history  MOJ 法規沿革 page -> data/med/raw/moj/<pcode>-history.html (read by moj_history.fetch via patched RAW)
  english  MOJ official English text (current version) -> data/med/raw/moj_en/<pcode>.html + english_titles.json
  current  MOJ current Chinese text -> data/med/raw/moj_all/<pcode>.html (used to check the store's current version)
"""
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from medcfg import RAW_LY, RAW_MOJ, RAW_MOJ_ALL, RAW_MOJ_EN, polite_get, write_atomic  # noqa: E402
import registry_med  # noqa: E402

API = "https://ly.govapi.tw/v2"


def get_json(path: str, **params) -> dict:
    url = f"{API}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    return json.loads(polite_get(url))


def fetch_law(law_id: str) -> tuple[int, int]:
    out = RAW_LY / law_id
    meta_f = out / "_law.json"
    if meta_f.exists():
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        versions = meta["versions"]
    else:
        law = get_json(f"laws/{law_id}")
        versions = get_json(f"laws/{law_id}/versions", limit=500)["lawversions"]
        write_atomic(meta_f, json.dumps({"law": law, "versions": versions}, ensure_ascii=False, indent=1))
    new = 0
    for v in versions:
        vid = v["版本編號"]
        f = out / (vid.split(":", 1)[1] + ".json")
        if f.exists():
            continue
        rows, page = [], 1
        while True:
            d = get_json("law_contents", 版本編號=vid, limit=500, page=page)
            rows += d["lawcontents"]
            if page >= d.get("total_page", 1):
                break
            page += 1
        write_atomic(f, json.dumps(rows, ensure_ascii=False))
        new += 1
    return len(versions), new


def fetch_page(url: str, f: Path) -> str:
    if not f.exists():
        write_atomic(f, polite_get(url))
    return f.read_text(encoding="utf-8", errors="ignore")


def english_title(page: str) -> str | None:
    m = re.search(r"Title：</th>\s*<td[^>]*>(.*?)</td>", page, re.S)
    if not m:
        return None
    t = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
    t = " ".join(t.split())
    t = re.sub(r"\s*\(?\s*CH\s*\)?\s*$", "", t, flags=re.I)  # trailing "CH" link label (link to the Chinese text)
    return t or None


def main(steps: list[str]) -> None:
    ids, codes = registry_med.lyids(), registry_med.pcodes()
    acts = [(t, ids[t], codes[ids[t]]) for t in registry_med.ACTS if ids.get(t) and codes.get(ids.get(t))]
    if "ly" in steps:
        for title, lid, _ in acts:
            n, new = fetch_law(lid)
            print(f"ly {lid} {title}: {n} versions, {new} downloaded now", flush=True)
    if "history" in steps:
        for title, lid, pc in acts:
            fetch_page(f"https://law.moj.gov.tw/LawClass/LawHistory.aspx?pcode={pc}", RAW_MOJ / f"{pc}-history.html")
            print("history", pc, title, flush=True)
    if "english" in steps:
        titles = registry_med.english_titles()
        for title, lid, pc in acts:
            try:
                page = fetch_page(f"https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode={pc}", RAW_MOJ_EN / f"{pc}.html")
                titles[lid] = english_title(page) or titles.get(lid, "")
            except RuntimeError as e:
                print("english failed", pc, e)
            print("english", pc, title, "->", titles.get(lid), flush=True)
        write_atomic(registry_med.EN_TITLES, json.dumps(titles, ensure_ascii=False, indent=1))
    if "current" in steps:
        for title, lid, pc in acts:
            fetch_page(f"https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode={pc}", RAW_MOJ_ALL / f"{pc}.html")
            print("current", pc, title, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:] or ["ly", "history", "english", "current"])
