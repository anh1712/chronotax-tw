"""Insert the generated tables into docs/AUDIT_DATES.md (markers <!--VERDICT_TABLE--> and <!--SUMMARY_TABLE-->).

  python -I -B src/audit/fill_report.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, ROOT  # noqa: E402

doc = ROOT / "docs" / "AUDIT_DATES.md"
s = doc.read_text(encoding="utf-8")
for marker, f in (("<!--VERDICT_TABLE-->", "verdicts_table.md"), ("<!--SUMMARY_TABLE-->", "summary_numbers.md")):
    assert marker in s, marker
    s = s.replace(marker, (OUT / f).read_text(encoding="utf-8").strip())
doc.write_text(s, encoding="utf-8")
print("filled", doc)
