"""Phase 4: weekly product pulse (<=250 words).   Code writes the skeleton and every number;
the LLM fills only the blanks (one sentence per theme, one observation, three actions) and may
not type a digit. Quotes are copied from the CSV by code. Limits are enforced by counting.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from src.llm import chat_json

MAX_WORDS, MAX_TRIES = 250, 3
SAMPLE, ASSIGN = Path("data/reviews_sample.csv"), Path("data/theme_assignments.csv")
THEMES, FEE = Path("outputs/themes.json"), Path("outputs/fee_issue.json")
OUT_MD, OUT_JSON = Path("outputs/weekly_pulse.md"), Path("outputs/pulse_parts.json")
FEE_LABEL = {"brokerage": "Brokerage", "dp_charges": "DP charges", "amc_charges": "AMC charges",
             "exit_load": "Exit load", "gst_taxes": "GST / taxes", "platform_fee": "Platform fee",
             "account_charges": "Account charges", "margin_interest": "Margin interest",
             "withdrawal_charges": "Withdrawal charges"}
HAS_DIGIT = re.compile(r"\d")


def words(text: str) -> int:
    return len(text.split())          # strict: counts markdown tokens too


def short_quote(full: str, quote: str, review_id: str) -> str:
    """Return a 10-25 word stretch that provably exists in the review text."""
    if 10 <= words(quote) <= 25 and quote in full:
        return quote
    for attempt in range(MAX_TRIES):
        out = chat_json([{"role": "user", "content": (
            "Copy ONE contiguous stretch of 10 to 25 words from this review, exactly as written "
            f'(same characters, no edits). Return JSON {{"substring":"..."}}.\n\nReview: {full}')}],
            nocache_salt=f"sq{attempt}")
        sub = (out.get("substring") or "").strip()
        if sub and sub in full and 10 <= words(sub) <= 25:
            return sub
    toks = full.split(" ")                      # deterministic fallback: first 25 words, still verbatim
    return " ".join(toks[:25])


def trend(df: pd.DataFrame, theme_id: str) -> str:
    wk = sorted(df.week_start.unique())
    recent, prev = wk[-4:], wk[-8:-4]
    g = df[(df.theme == theme_id) & (df.rating <= 2)]
    a, b = int(g.week_start.isin(recent).sum()), int(g.week_start.isin(prev).sum())
    return f"last 4 weeks {a} vs {b} before"


def build_skeleton(top, df, fee, n_reviews, week_label):
    blocks = []
    for i, t in enumerate(top, 1):
        q = t["quote"]
        blocks.append({
            "head": (f"{i}. **{t['name']}**: {t['low_star']} of {t['total']} are 1-2 star "
                     f"({t['low_share']:.0%}); {trend(df, t['id'])}."),
            "quote": f"> \"{q['quote_short']}\" ({q['rating']}-star, {q['date']})",
            "id": t["id"]})
    issue = fee["fee_issue"]
    conf_total = fee["stance_counts"]["confused"]
    fee_line = (f"**{FEE_LABEL.get(issue, issue)}** confuses users: {fee['confused_by_fee'][issue]} of "
                f"{conf_total} confused fee reviews.")
    return blocks, fee_line


def fill(top, quotes, extra: str, attempt: int) -> dict:
    qtxt = "\n".join(f"{t['id']} ({t['name']}): \"{quotes[t['id']]}\"" for t in top)
    return chat_json([
        {"role": "system", "content": "You write terse product-pulse copy for a PM. NEVER type any digit "
         "or number (write words instead if you must). Do not invent facts beyond the quotes."},
        {"role": "user", "content": (
            "Themes with one user quote each:\n" + qtxt + "\n\nReturn JSON with exactly:\n"
            '{"theme_lines":{"T1":"<one sentence, max 14 words, what users are saying>", ...one per theme id above},'
            '"observation":"<one sentence, max 25 words, connecting the themes>",'
            '"actions":["<action 1>","<action 2>","<action 3>"]}\n'
            "Each action: max 18 words, starts with a verb, and responds to something specific in ONE "
            "theme's quote (e.g. 'add a way to reach a human when the bot fails', not 'improve support'). "
            "Exactly three actions, no digits anywhere." + extra)}],
        nocache_salt=f"pulse{attempt}")


def validate(parts: dict, top) -> list[str]:
    errs = []
    ids = [t["id"] for t in top]
    lines = parts.get("theme_lines", {})
    acts = parts.get("actions", [])
    if any(i not in lines for i in ids):
        errs.append("missing theme line")
    if not isinstance(acts, list) or len(acts) != 3:
        errs.append("need exactly 3 actions")
    texts = list(lines.values()) + [parts.get("observation", "")] + (acts if isinstance(acts, list) else [])
    if any(HAS_DIGIT.search(str(x)) for x in texts):
        errs.append("LLM text contains a digit")
    return errs


def render(week_label, n_reviews, blocks, lines, fee_line, obs, acts, fee):
    out = [f"# Weekly Product Pulse - {week_label}",
           f"Groww Play Store: {n_reviews} reviews, 12 weeks.", "", "## Top themes"]
    for b in blocks:
        out += [b["head"] + " " + lines[b["id"]], b["quote"], ""]
    out += ["## Key observation", obs, "", "## Fee watch", fee_line, "", "## Actions"]
    out += [f"{i}. {a}" for i, a in enumerate(acts, 1)]
    return "\n".join(out) + "\n"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    df = pd.read_csv(SAMPLE).merge(pd.read_csv(ASSIGN), on="review_id")
    th, fee = json.loads(THEMES.read_text(encoding="utf-8")), json.loads(FEE.read_text(encoding="utf-8"))
    top = [t for t in th["themes"] if t["id"] in th["top"]]
    by_id = df.set_index("review_id")
    for t in top:
        q = t["quote"]
        full = by_id.loc[q["review_id"], "text"]
        q["quote_short"] = short_quote(full, q["quote"], q["review_id"])
        assert q["quote_short"] in full, "quote not verbatim"
    quotes = {t["id"]: t["quote"]["quote_short"] for t in top}

    wk = sorted(df.week_start.unique())
    week_label = f"week of {wk[-1]} (data through {date.today():%Y-%m-%d})"
    blocks, fee_line = build_skeleton(top, df, fee, len(df), week_label)

    extra, text, errs, parts = "", "", [], {}
    for attempt in range(MAX_TRIES):
        parts = fill(top, quotes, extra, attempt)
        errs = validate(parts, top)
        if not errs:
            text = render(week_label, len(df), blocks, parts["theme_lines"], fee_line,
                          parts["observation"], parts["actions"], fee)
            n = words(text)
            print(f"attempt {attempt + 1}: {n} words")
            if n <= MAX_WORDS:
                break
            errs = [f"over limit ({n} words)"]
            extra = f"\nPREVIOUS DRAFT WAS TOO LONG ({n} words total). Make every sentence shorter."
        else:
            print(f"attempt {attempt + 1}: rejected -> {errs}")
            extra = f"\nPREVIOUS DRAFT REJECTED: {errs}. Fix this."
    status = "OK" if not errs and words(text) <= MAX_WORDS else "FAILED LIMITS"
    OUT_MD.write_text(text, encoding="utf-8")
    OUT_JSON.write_text(json.dumps({"week_label": week_label, "top_themes": [t["name"] for t in top],
                                    "fee_issue": fee["fee_issue"], "status": status}, indent=2),
                        encoding="utf-8")
    print(f"\n{text}\nwords: {words(text)}/{MAX_WORDS} | actions: {len(parts.get('actions', []))} | status: {status}")


if __name__ == "__main__":
    main()
