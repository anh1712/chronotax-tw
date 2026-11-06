"""Which Taiwan laws are in the store, and how they map between sources.

LY ids come from LYAPI (`laws?主管機關=財政部`, status 現行, taxation-related; organisation acts, bond acts and
treasury acts are excluded). MOJ pcodes are resolved once by title from law.moj.gov.tw search and cached in
data/raw/moj/pcodes.json (`python src/registry.py resolve`).
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PCODES = ROOT / "data" / "raw" / "moj" / "pcodes.json"
UA = {"User-Agent": "LAW-TW research prototype"}

# LY law id → (Chinese title, English short title). Core pilot first.
LAWS: dict[str, tuple[str, str]] = {
    "01513": ("所得稅法", "Income Tax Act"),
    "01526": ("所得基本稅額條例", "Income Basic Tax Act"),
    "01521": ("加值型及非加值型營業稅法", "Value-added and Non-value-added Business Tax Act"),
    "01512": ("稅捐稽徵法", "Tax Collection Act"),
    "01655": ("納稅者權利保護法", "Taxpayer Rights Protection Act"),
    "01515": ("遺產及贈與稅法", "Estate and Gift Tax Act"),
    "01519": ("土地稅法", "Land Tax Act"),
    "01524": ("房屋稅條例", "House Tax Act"),
    "01525": ("契稅條例", "Deed Tax Act"),
    "01516": ("印花稅法", "Stamp Tax Act"),
    "01522": ("使用牌照稅法", "Vehicle License Tax Act"),
    "01527": ("娛樂稅法", "Amusement Tax Act"),
    "01517": ("貨物稅條例", "Commodity Tax Act"),
    "01622": ("菸酒稅法", "Tobacco and Alcohol Tax Act"),
    "08148": ("特種貨物及勞務稅條例", "Specifically Selected Goods and Services Tax Act"),
    "01518": ("證券交易稅條例", "Securities Transaction Tax Act"),
    "01626": ("期貨交易稅條例", "Futures Transaction Tax Act"),
    "01528": ("關稅法", "Customs Act"),
    "01613": ("地方稅法通則", "Local Tax Act"),
    "07158": ("境外資金匯回管理運用及課稅條例", "Management, Utilization, and Taxation of Repatriated Offshore Funds Act"),
    "01509": ("財務罰鍰處理暫行條例", "Provisional Act Governing Financial Fines"),
    "01587": ("記帳士法", "Certified Bookkeepers Act"),
    "08128": ("產業創新條例", "Statute for Industrial Innovation"),
}


def resolve_pcode(title: str) -> str | None:
    url = "https://law.moj.gov.tw/Law/LawSearchResult.aspx?ty=ONEBAR&kw=" + urllib.parse.quote(title)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        page = r.read().decode("utf-8", errors="ignore")
    for m in re.finditer(r'title="([^"]+)" href="[^"]*pcode=([A-Z0-9]+)', page):
        if m.group(1) == title:  # exact title only; never guess
            return m.group(2)
    return None


def pcodes() -> dict[str, str]:
    return json.loads(PCODES.read_text(encoding="utf-8")) if PCODES.exists() else {}


if __name__ == "__main__" and sys.argv[1:] == ["resolve"]:
    sys.stdout.reconfigure(encoding="utf-8")
    known = pcodes()
    for lid, (title, _) in LAWS.items():
        if lid not in known:
            known[lid] = resolve_pcode(title)
        print(lid, title, known[lid])
    PCODES.parent.mkdir(parents=True, exist_ok=True)
    PCODES.write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
