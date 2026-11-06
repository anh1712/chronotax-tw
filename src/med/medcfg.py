"""ChronoMed-TW shared configuration: paths, the list of health/medical acts, and a polite HTTP client.

ChronoMed-TW reuses the ChronoTax-TW pipeline (src/*.py) WITHOUT editing it. Every original module keeps its own
paths (data/lawtw.db, data/raw/...); the wrappers in src/med/ re-point those module constants to data/med/ before
calling the original functions. Nothing here writes outside data/med/.

Politeness rules for government / open-data servers (agent rules §3): one process, at most one request every
MIN_INTERVAL seconds, retries with exponential backoff, every response cached on disk (re-runs fetch nothing),
every request logged to data/med/raw/fetch_log.tsv.
"""
import datetime as dt
import sys
import time
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True  # importing src/*.py must not write .pyc files into the original src/__pycache__

ROOT = Path(__file__).resolve().parent.parent.parent        
SRC = ROOT / "src"
MED_SRC = SRC / "med"
MED = ROOT / "data" / "med"
RAW = MED / "raw"
RAW_LY = RAW / "ly"
RAW_MOJ = RAW / "moj"
RAW_MOJ_EN = RAW / "moj_en"
RAW_MOJ_ALL = RAW / "moj_all"
DB = MED / "medtw.db"
BENCH = MED / "bench"
RESULTS = MED / "results"
FIGS = MED / "figures"
PCODES = RAW_MOJ / "pcodes.json"
LYIDS = RAW_LY / "lyids.json"
TAX_DB = ROOT / "data" / "lawtw.db"                       # ChronoTax store: opened READ-ONLY, never written
TAX_BENCH = ROOT / "data" / "bench" / "tw_taxtime_v0.jsonl"  # read-only

for p in (SRC, MED_SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Health/medical acts (all under 衛生福利部). Chosen for many versions and changing amounts/conditions; titles must
# match the Legislative Yuan and MOJ titles exactly (resolution never guesses). English titles are filled from the
# official MOJ English page when it exists (see registry_med.py); these are placeholders until then.
ACTS: list[str] = [
    "全民健康保險法",        # National Health Insurance; 2011 "二代健保" full revision, in force 2013-01-01
    "醫療法",
    "藥事法",
    "醫師法",
    "護理人員法",
    "長期照顧服務法",
    "傳染病防治法",
    "菸害防制法",
    "食品安全衛生管理法",
    "精神衛生法",
    "醫療器材管理法",
    "病人自主權利法",
    "安寧緩和醫療條例",
    "人體器官移植條例",
    "緊急醫療救護法",
    "藥害救濟法",
    "罕見疾病防治及藥物法",
    "藥師法",
    "管制藥品管理條例",
    "健康食品管理法",
]

UA = {"User-Agent": "LAW-TW research prototype / ChronoMed-TW (contact via GitHub anh1712)"}
MIN_INTERVAL = 1.1  # seconds between two requests (rule: <= 1 request/second)
_last = [0.0]
FETCH_LOG = RAW / "fetch_log.tsv"


def polite_get(url: str, timeout: int = 90, tries: int = 4) -> bytes:
    """GET with a global rate limit, exponential backoff, and a request log. Raises after `tries` failures."""
    RAW.mkdir(parents=True, exist_ok=True)
    for attempt in range(tries):
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                data = r.read()
            _log(url, "ok", len(data), time.monotonic() - t0)
            return data
        except Exception as e:  # network hiccup or server error: back off, then give up loudly
            _log(url, f"err:{type(e).__name__}:{str(e)[:80]}", 0, time.monotonic() - t0)
            if attempt == tries - 1:
                raise RuntimeError(f"GET {url} failed after {tries} tries: {e}") from e
            time.sleep(min(120, 5 * 2 ** attempt))


def _log(url: str, status: str, n: int, secs: float) -> None:
    with FETCH_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}\t{status}\t{n}\t{secs:.2f}\t{url}\n")


def write_atomic(path: Path, data: bytes | str) -> None:
    """Write via a temp file + rename, so an interrupted run never leaves a half-written cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    if isinstance(data, str):
        tmp.write_text(data, encoding="utf-8")
    else:
        tmp.write_bytes(data)
    tmp.replace(path)


def _redirect_original_paths() -> None:
    """Safety net, run at import: every path constant of the ORIGINAL modules that could be written to (or read as the
    store) is re-pointed into data/med/, so no call from this package can touch data/raw/, data/lawtw.db or data/bench/.
    (Lesson: an early scratch script called moj_history.fetch() before re-pointing RAW and wrote 20 pages into
    data/raw/moj/; they were removed and this redirect was added.) The original files are not modified."""
    import bench
    import build_db
    import english
    import eval_retrieval
    import fetch_ly
    import moj_history
    import query
    import registry

    moj_history.RAW = RAW_MOJ
    fetch_ly.RAW = RAW_LY
    build_db.RAW = RAW_LY
    build_db.DB = DB
    english.RAW = RAW_MOJ_EN
    english.DB = DB
    bench.DB = DB
    bench.OUT = BENCH / "_gen"
    query.DB = DB
    eval_retrieval.DB = DB
    eval_retrieval.ROOT = MED          # eval_retrieval.main() writes ROOT/data/bench/...: never call it; if called, stays here
    eval_retrieval.BENCH = BENCH / "tw_medtime_v0.jsonl"
    registry.PCODES = PCODES


_redirect_original_paths()


def patch_pipeline() -> None:
    """Re-point the ORIGINAL pipeline modules (src/*.py) at the medical acts (paths are already redirected above).
    Only the in-memory module attributes of this process change."""
    import build_db
    import english
    import registry_med

    laws = registry_med.laws()
    codes = registry_med.pcodes()
    build_db.LAWS = laws
    build_db.pcodes = lambda: codes
    english.LAWS = laws
    english.pcodes = lambda: codes
