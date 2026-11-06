"""TW-MedTime v0: the TW-TaxTime generator (src/bench.py, unchanged, same seed 19) run on the medical store.

  python -I src/med/bench_med.py   -> data/med/bench/tw_medtime_v0.jsonl + data/med/bench/summary_medtime.json

bench.main() is called as is; only its DB/OUT constants point to data/med/ (medcfg). It writes tw_taxtime_v0.jsonl and
summary.json into data/med/bench/_gen/; this wrapper renames the file, re-prefixes ids "tt-" -> "mt-", and removes _gen.
Zero LLM calls; every gold answer is an article-version id (or amount) checked by rule.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medcfg  # noqa: E402
from medcfg import BENCH, write_atomic  # noqa: E402
import bench  # noqa: E402  original generator


def main(seed: int = 19) -> dict:
    medcfg.patch_pipeline()
    gen = BENCH / "_gen"
    bench.DB, bench.OUT = medcfg.DB, gen
    bench.main(seed)
    items = [json.loads(line) for line in (gen / "tw_taxtime_v0.jsonl").open(encoding="utf-8")]
    for it in items:
        it["id"] = "mt-" + it["id"][3:]
    write_atomic(BENCH / "tw_medtime_v0.jsonl", "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items))
    summary = json.loads((gen / "summary.json").read_text(encoding="utf-8"))
    summary["source"] = "src/bench.py main() on data/med/medtw.db"
    write_atomic(BENCH / "summary_medtime.json", json.dumps(summary, ensure_ascii=False, indent=1))
    shutil.rmtree(gen)
    return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(main())
