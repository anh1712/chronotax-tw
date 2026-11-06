"""Build tax-store variants in data/audit/ with the pipeline code, never touching data/lawtw.db.

  python -I -B src/audit/build_variants.py original   -> data/audit/lawtw_rebuilt_original.db  (src/*.py unchanged)
  python -I -B src/audit/build_variants.py fixed      -> data/audit/lawtw_fixed.db  (src/audit/patched/moj_history.py +
                                                         src/audit/patched/build_db.py, i.e. fix_moj_history.patch)
  python -I -B src/audit/build_variants.py fixed_ab   -> data/audit/lawtw_fixed_ab.db  (the above + Fix B,
                                                         src/audit/patched_b/effect_rules.py = fix_effect_rules.patch)
Each variant runs build_db.build(), then english.main() and regulations.main() (as the current lawtw.db had them),
reading only the cached pages in data/raw/ (any network fetch raises). One variant per process, because the two
variants need different `moj_history` modules.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import AUDIT, FIXED_DB, RAW, REBUILT_DB  # noqa: E402


def no_fetch(*_a, **_k):
    raise RuntimeError("network fetch attempted during audit build")


def main(variant: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if variant in ("fixed", "fixed_ab"):
        sys.path.insert(0, str(common.SRC / "audit" / "patched"))  # patched moj_history + build_db win over src/
        target = FIXED_DB
        if variant == "fixed_ab":  # + Fix B: patched effect_rules (multi-amendment commencement sentences)
            sys.path.insert(0, str(common.SRC / "audit" / "patched_b"))
            target = AUDIT / "lawtw_fixed_ab.db"
    elif variant == "original":
        target = REBUILT_DB
    else:
        sys.exit("variant: original | fixed | fixed_ab")
    import build_db  # noqa: E402
    import english  # noqa: E402
    import moj_history  # noqa: E402
    import regulations  # noqa: E402
    import effect_rules  # noqa: E402
    print("build_db from", build_db.__file__, "| moj_history from", moj_history.__file__, "| effect_rules from",
          effect_rules.__file__)
    assert Path(target).resolve().parent == AUDIT.resolve()
    # read-only cached sources; every write goes to `target`
    build_db.RAW = RAW / "ly"
    build_db.DB = target
    moj_history.RAW = RAW / "moj"
    _orig_fetch = moj_history.fetch

    def cached_history(pcode: str) -> str:
        f = RAW / "moj" / f"{pcode}-history.html"
        if not f.exists():
            no_fetch()
        return f.read_text(encoding="utf-8", errors="ignore")

    moj_history.fetch = cached_history
    english.DB = target
    english.RAW = RAW / "moj_en"
    regulations.DB = target
    regulations.RAW = RAW / "moj_reg"
    for mod in (english, regulations):
        orig = mod.fetch

        def cached(pcode, _orig=orig, _mod=mod):
            f = (_mod.RAW / f"{pcode}.html")
            if not f.exists():
                no_fetch()
            return f.read_text(encoding="utf-8", errors="ignore")
        mod.fetch = cached
    build_db.build()
    english.main()
    regulations.main()
    print("written", target)


if __name__ == "__main__":
    main(sys.argv[1])
