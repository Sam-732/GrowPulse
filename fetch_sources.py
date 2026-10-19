"""Phase 5a: download the official Groww pages as plain text (the 'book' for the fee explainer).

URLs are hardcoded here; the LLM never writes a URL. Pages that return identical text are de-duplicated.
"""
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import httpx
import truststore
from bs4 import BeautifulSoup

truststore.inject_into_ssl()

SOURCES = [
    ("pricing", "Groww Pricing - Brokerage Charges & Pricing", "https://groww.in/pricing"),
    ("help_delivery", "Groww Help - What is the charge for buy order (delivery)?",
     "https://groww.in/help/stocks,-f&o,-ipo-&-mtf/sx-pricing/what-is-the-charge-for-buy-order-delivery"),
    ("help_intraday", "Groww Help - What are intraday charges?",
     "https://groww.in/help/stocks,-f&o,-ipo-&-mtf/sx-pricing/what-are-intraday-charges"),
    ("help_over20", "Groww Help - Why is my brokerage more than 20 rupees?",
     "https://groww.in/help/payments-&-withdrawals/payments-charges/why-is-my-brokerage-more-than-20-rupees--71"),
    ("help_howmuch", "Groww Help - How much does Groww charge for stocks?",
     "https://groww.in/help/stocks,-f&o,-ipo-&-mtf/sx-demat-account/how-much-does-groww-charge-for-stocks-1"),
]
OUTDIR = Path("data/sources")
HEADERS = {"User-Agent": "Mozilla/5.0 (review-pulse educational project)"}


def page_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        t.decompose()
    return re.sub(r"[ \t]+", " ", soup.get_text("\n", strip=True))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    kept, seen = [], {}
    for sid, title, url in SOURCES:
        try:
            r = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"FAIL {sid}: {e}")
            continue
        text = page_text(r.text)
        h = hashlib.sha256(text.encode()).hexdigest()
        if h in seen:
            print(f"DUPLICATE {sid} == {seen[h]} (dropped)")
            continue
        seen[h] = sid
        (OUTDIR / f"{sid}.txt").write_text(text, encoding="utf-8")
        kept.append({"id": sid, "title": title, "url": url, "chars": len(text),
                     "fetched": date.today().isoformat()})
        print(f"OK   {sid:14} {len(text):6} chars  {url}")
    Path("data/sources.json").write_text(json.dumps(kept, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
