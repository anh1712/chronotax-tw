"""Attach the official MOJ English text (current version only) to data/med/medtw.db: src/english.py, unchanged,
re-pointed at the medical acts and the cached pages in data/med/raw/moj_en (fetched politely by fetch_med.py).

  python -I src/med/english_med.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402
import english  # noqa: E402  original

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    medcfg.patch_pipeline()
    missing = [pc for pc in english.pcodes().values() if not (medcfg.RAW_MOJ_EN / f"{pc}.html").exists()]
    if missing:
        sys.exit(f"run fetch_med.py english first; missing {missing}")  # english.fetch would download without our log
    english.main()
