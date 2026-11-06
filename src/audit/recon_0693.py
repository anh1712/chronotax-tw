"""Step 4: why does the published temporal R@1 0.693 differ from today's 0.697?

  python -I -B src/audit/recon_0693.py   -> data/audit/recon/* , data/audit/out/recon_0693.json

Rebuilds every combination of the code that existed on 2026-10-20 (from git, copied into src/audit/recon/):
  store code   B0 = build_db@6077033 (before "overtaken")   B1 = build_db@d652f40 (= today)
  bench code   P0 = bench@4052245 (README first shows 0.693)  P1 = bench@6077033  P2 = bench@6290fd1 (= today)
  regulations  +reg = regulations.py appended (as data/lawtw.db today) / none
and evaluates the amount probes with eval_retrieval (unchanged since 4052245). Raw inputs are the cached files in
data/raw (read-only, unchanged since 2026-10-19). Also compares each generated bench with data/bench/tw_taxtime_v0.jsonl.
"""
import importlib.util
import json
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import AUDIT, BENCH, OUT, RAW, write_json  # noqa: E402

import eval_retrieval  # noqa: E402  original
import moj_history  # noqa: E402  original
import regulations  # noqa: E402
import english  # noqa: E402

RECON = AUDIT / "recon"
CODE = common.SRC / "audit" / "recon"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cached(mod_raw: Path):
    def f(pcode):
        p = mod_raw / f"{pcode}.html"
        if not p.exists():
            raise RuntimeError("fetch attempted")
        return p.read_text(encoding="utf-8", errors="ignore")
    return f


def build(code: Path, db: Path) -> None:
    m = load(code, "bd_" + code.stem)
    m.RAW, m.DB = RAW / "ly", db
    moj_history.fetch = lambda pc: (RAW / "moj" / f"{pc}-history.html").read_text(encoding="utf-8", errors="ignore")
    m.build()


def add_regulations(src: Path, dst: Path) -> None:
    shutil.copyfile(src, dst)
    english.DB, english.RAW, english.fetch = dst, RAW / "moj_en", cached(RAW / "moj_en")
    regulations.DB, regulations.RAW, regulations.fetch = dst, RAW / "moj_reg", cached(RAW / "moj_reg")
    english.main()
    regulations.main()


def gen_bench(code: Path, db: Path, outdir: Path) -> Path:
    b = load(code, "bench_" + code.stem + "_" + db.stem)
    b.DB, b.OUT = db, outdir
    b.main()
    return outdir / "tw_taxtime_v0.jsonl"


def evaluate(db: Path, bench: Path) -> dict:
    items = [json.loads(l) for l in bench.open(encoding="utf-8")]
    items = [i for i in items if i["type"] == "amount"]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    return {m: eval_retrieval.run(con, items, m) for m in eval_retrieval.MODES}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    RECON.mkdir(parents=True, exist_ok=True)
    dbs = {"B0": RECON / "B0.db", "B1": RECON / "B1.db"}
    build(CODE / "build_db_6077033.py", dbs["B0"])
    build(common.SRC / "build_db.py", dbs["B1"])
    dbs["B1+reg"] = RECON / "B1reg.db"
    add_regulations(dbs["B1"], dbs["B1+reg"])
    benches = {"P0": CODE / "bench_4052245.py", "P1": CODE / "bench_6077033.py", "P2": common.SRC / "bench.py"}
    res = {"published": json.loads((BENCH / "results_retrieval.json").read_text(encoding="utf-8")), "cells": {}}
    today = BENCH / "tw_taxtime_v0.jsonl"
    today_amount = [l for l in today.open(encoding="utf-8") if '"type": "amount"' in l]
    gen = {}
    for bn, code in benches.items():
        for dn in ("B0", "B1"):
            p = gen_bench(code, dbs[dn], RECON / f"bench_{bn}_{dn}")
            gen[(bn, dn)] = p
            amount = [l for l in p.open(encoding="utf-8") if '"type": "amount"' in l]
            res["cells"][f"{bn} on {dn}"] = {
                "amount_probes": len(amount),
                "identical_to_data_bench_file": p.read_bytes() == today.read_bytes(),
                "amount_lines_identical_to_data_bench": amount == today_amount}
    for (bn, dn), p in gen.items():
        for target in ([dn] if dn == "B0" else ["B1", "B1+reg"]):
            r = evaluate(dbs[target], p)
            res["cells"].setdefault(f"{bn} on {dn}", {})[f"eval on {target}"] = {
                m: [r[m]["R@1"], r[m]["R@5"], r[m]["misgrounding@1"]] for m in r}
    for target in ("B0", "B1", "B1+reg"):
        r = evaluate(dbs[target], today)
        res["cells"][f"data/bench file on {target}"] = {m: [r[m]["R@1"], r[m]["R@5"], r[m]["misgrounding@1"]] for m in r}
    write_json(OUT / "recon_0693.json", res)
    pub = {m: [v["R@1"], v["R@5"], v["misgrounding@1"]] for m, v in res["published"].items()}
    print("published results_retrieval.json:", pub)
    for k, v in res["cells"].items():
        print(k, json.dumps(v, ensure_ascii=False))


if __name__ == "__main__":
    main()
