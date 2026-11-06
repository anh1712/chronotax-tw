"""Rebuild ChronoMed-TW end to end (0 LLM calls, CPU only):   python -I src/med/run_all.py [--fetch]

  [fetch_med: LYAPI versions, MOJ history/English/current pages; polite, cached, resumable]
  -> registry_med resolve (cached) -> build_med (ChronoMed store) -> build_med --tax-parser (original pipeline, same data)
  -> english_med -> stats_med -> bench_med (TW-MedTime) -> eval_med -> window_med -> handcheck_med -> examples_med
  -> figures_med (matplotlib)
Every step reads/writes only data/med/ (the tax store and its probes are opened read-only).
"""
import subprocess
import sys
from pathlib import Path

MED = Path(__file__).resolve().parent
STEPS = [["build_med.py"], ["build_med.py", "--tax-parser"], ["english_med.py"], ["stats_med.py"], ["bench_med.py"],
         ["eval_med.py"], ["window_med.py"], ["handcheck_med.py"], ["examples_med.py"], ["figures_med.py"]]

if __name__ == "__main__":
    steps = ([["registry_med.py", "resolve"], ["fetch_med.py"]] if "--fetch" in sys.argv else []) + STEPS
    for s in steps:
        print("==", " ".join(s), flush=True)
        r = subprocess.run([sys.executable, "-I", str(MED / s[0]), *s[1:]], stdout=subprocess.DEVNULL)
        if r.returncode:
            sys.exit(f"{s} failed ({r.returncode})")
    print("done: results in data/med/results, probes in data/med/bench, figures in data/med/figures")
