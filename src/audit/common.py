"""Shared paths and helpers for the date audit (agent: date-audit). Writes ONLY under data/audit/.

Read-only inputs: data/lawtw.db (never opened here; we work on the byte copy data/audit/lawtw_current_copy.db),
data/raw/, data/bench/, data/med/, data/verifier/, src/*.py, src/med/*.py (imported, never edited).
"""
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never write .pyc files into src/__pycache__ or src/med/__pycache__

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
MED_SRC = SRC / "med"
AUDIT = ROOT / "data" / "audit"
OUT = AUDIT / "out"
RAW_AUDIT = AUDIT / "raw"  # cache of live MOJ pages fetched by this audit
RAW = ROOT / "data" / "raw"  # read-only
BENCH = ROOT / "data" / "bench"  # read-only
CUR_DB = AUDIT / "lawtw_current_copy.db"  # byte copy of data/lawtw.db (sha256 checked)
REBUILT_DB = AUDIT / "lawtw_rebuilt_original.db"  # original build_db code, rebuilt here (determinism check)
FIXED_DB = Path(os.environ.get("AUDIT_FIXED_DB", AUDIT / "lawtw_fixed.db"))  # corrected store (Fix A; or A+B)
TAG = os.environ.get("AUDIT_TAG", "")  # suffix of output files for the A+B variant ("_ab")

for p in (SRC,):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def ro(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def tax_pages() -> dict[str, tuple[str, str]]:
    """law_id -> (pcode, cached MOJ history page) for the 23 tax acts of src/registry.py (read-only)."""
    from registry import LAWS
    codes = json.loads((RAW / "moj" / "pcodes.json").read_text(encoding="utf-8"))
    return {lid: (codes[lid], (RAW / "moj" / f"{codes[lid]}-history.html").read_text(encoding="utf-8", errors="ignore"))
            for lid in LAWS}


def ly_meta(law_id: str) -> dict:
    return json.loads((RAW / "ly" / law_id / "_law.json").read_text(encoding="utf-8"))
