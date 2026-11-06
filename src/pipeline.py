"""Rebuild everything in order (0 LLM tokens):  python -I src/pipeline.py [--fetch]

  [fetch_ly]  → build_db → english → regulations → bench → eval_retrieval
Reranker training/eval (GPU) and the natural-language benchmark (LLM) are separate:
  .venv/Scripts/python src/rerank.py data|train MIX|eval      python -I src/nl_bench.py gen N | eval
"""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
STEPS = ["build_db.py", "english.py", "regulations.py", "bench.py", "eval_retrieval.py"]

if __name__ == "__main__":
    steps = (["fetch_ly.py"] if "--fetch" in sys.argv else []) + STEPS
    for s in steps:
        print(f"== {s}", flush=True)
        r = subprocess.run([sys.executable, "-I", str(SRC / s)])
        if r.returncode:
            sys.exit(f"{s} failed ({r.returncode})")
