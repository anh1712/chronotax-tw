"""Download every version (full text) of selected Taiwan laws from LYAPI v2 into data/raw/ly/<law_id>/.

LYAPI (https://ly.govapi.tw/v2/, OpenFun, data CC BY 4.0) mirrors Legislative Yuan records. Each version is
the FULL text of the law at that version; `版本追蹤` says in which version an article's text last changed.
Version dates are Legislative Yuan passage dates (三讀), not promulgation/effective dates — see build_db.py.

Usage: python src/fetch_ly.py [law_id ...]   (default: every law in registry.LAWS)
Re-running only downloads versions not yet on disk.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://ly.govapi.tw/v2"
UA = {"User-Agent": "LAW-TW research prototype (contact via GitHub anh1712)"}
RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "ly"


def get(path: str, **params) -> dict:
    url = f"{API}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:  # network hiccup: back off, then give up loudly
            if attempt == 2:
                raise RuntimeError(f"GET {url} failed: {e}") from e
            time.sleep(3 * (attempt + 1))


def fetch_law(law_id: str) -> None:
    out = RAW / law_id
    out.mkdir(parents=True, exist_ok=True)
    meta = get(f"laws/{law_id}")
    versions = get(f"laws/{law_id}/versions", limit=500)["lawversions"]
    (out / "_law.json").write_text(json.dumps({"law": meta, "versions": versions}, ensure_ascii=False, indent=1), encoding="utf-8")
    new = 0
    for v in versions:
        vid = v["版本編號"]
        f = out / (vid.split(":", 1)[1] + ".json")
        if f.exists():
            continue
        rows, page = [], 1
        while True:
            d = get("law_contents", 版本編號=vid, limit=500, page=page)
            rows += d["lawcontents"]
            if page >= d.get("total_page", 1):
                break
            page += 1
        f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        new += 1
        time.sleep(0.5)
    print(f"{law_id}: {len(versions)} versions, {new} downloaded now")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from registry import LAWS
    for lid in sys.argv[1:] or list(LAWS):
        fetch_law(lid)
