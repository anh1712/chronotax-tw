"""Corrected history reader (src/audit/patched/moj_history.py) vs original vs P3, on all 413 tax entries.

  python -I -B src/audit/check_patched_reader.py   -> data/audit/out/patched_reader_check.json (+ console)

Lists every entry where the corrected reader's MAIN date differs from the original reader, every entry with
per-article rules / paragraph-level exceptions / delegated dates, and the corrected reading of the 31 entries.
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import MED_SRC, OUT, tax_pages, write_json  # noqa: E402

import moj_history  # noqa: E402  original

sys.path.insert(0, str(MED_SRC))
import moj_med  # noqa: E402  P3


def load_patched(name: str = "moj_history_patched"):
    spec = importlib.util.spec_from_file_location(name, common.SRC / "audit" / "patched" / "moj_history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    fx = load_patched()
    rows, n = [], 0
    for lid, (pcode, page) in tax_pages().items():
        a = {e["no"]: e for e in moj_history.parse(page)}
        b = {e["no"]: e for e in moj_med.parse(page)}
        for e in fx.parse(page):
            n += 1
            o, p = a[e["no"]], b[e["no"]]
            assert o["promulgated"] == e["promulgated"]
            interesting = (e["effective"] != o["effective"] or o["effective"] != p["effective"] or e["rules"]
                           or e["partial"] or e["delegated"])
            if interesting:
                rows.append({"law_id": lid, "no": e["no"], "promulgated": e["promulgated"],
                             "orig": [o["effective"], o["effective_basis"]], "p3": [p["effective"], p["effective_basis"]],
                             "fixed": [e["effective"], e["effective_basis"]], "rules": e["rules"], "partial": e["partial"],
                             "delegated": e["delegated"], "main_differs_from_orig": e["effective"] != o["effective"],
                             "in_p3_31": o["effective"] != p["effective"], "note": e["note"][:400]})
    write_json(OUT / "patched_reader_check.json", {"entries": n, "rows": rows})
    d = [r for r in rows if r["main_differs_from_orig"]]
    print(f"entries {n}; interesting {len(rows)}; main date differs from original: {len(d)}; "
          f"of which in P3's 31: {sum(r['in_p3_31'] for r in d)}")
    for r in rows:
        tag = ("P3-31 " if r["in_p3_31"] else "      ") + ("MAIN≠ORIG" if r["main_differs_from_orig"] else "         ")
        print(f"{tag} {r['law_id']} #{r['no']} {r['promulgated']} orig {r['orig'][0]} | p3 {r['p3'][0]} | fixed "
              f"{r['fixed'][0]} ({r['fixed'][1]}) rules {[(x['ref'], x['effective']) for x in r['rules']]} "
              f"partial {[(x['refs'], x['effective']) for x in r['partial']]}{' DELEGATED' if r['delegated'] else ''}")


if __name__ == "__main__":
    main()
