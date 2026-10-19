"""Phase 3: fee-confusion detection.   AI labels, code counts.

Steps: keyword-filter the sample -> LLM labels each review (stance + specific fee)
-> code counts labels -> fee issue = most frequent specific fee among "confused".

SELECTION RULE (fixed before the first run):
  fee issue = the fee_type with the most "confused" reviews, ignoring "other"/"none".
  Tie-break A: more total fee-keyword reviews of that fee_type (any stance).
  Tie-break B: fee_type name, alphabetical.
  If nobody is "confused", no fee issue is declared (needs human decision).
"""
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from src.keywords import matched_keywords
from src.llm import chat_json

SAMPLE = Path("data/reviews_clean.csv" if "--full" in sys.argv else "data/reviews_sample.csv")
LABELS_CSV = Path("data/fee_labels.csv")
OUT = Path("outputs/fee_issue.json")
BATCH, TRUNC = 15, 300
STANCES = ["confused", "complaint_only", "praise", "unrelated"]
FEE_TYPES = ["brokerage", "dp_charges", "amc_charges", "exit_load", "gst_taxes",
             "platform_fee", "account_charges", "margin_interest", "withdrawal_charges",
             "other", "none"]
IGNORED = {"other", "none"}

STANCE_HELP = (
    "confused = does not understand what they were charged or why (asks, says unexpected/hidden/unclear/cut without notice)\n"
    "complaint_only = understands the charge but thinks it is too high or unfair\n"
    "praise = thinks charges are reasonable, low or zero\n"
    "unrelated = not about this app's fees/charges")
FEE_HELP = (
    "brokerage (per-order brokerage), dp_charges (depository charge on selling shares), amc_charges "
    "(demat annual maintenance), exit_load (mutual fund exit load), gst_taxes (GST/STT/stamp duty/taxes), "
    "platform_fee (platform/convenience/SIP/payment fee), account_charges (account opening/other account fees), "
    "margin_interest (MTF/margin interest), withdrawal_charges (withdrawal/payout/transfer charges), "
    "other (a fee not listed), none (no specific fee named)")


def label(rows: list) -> dict[str, dict]:
    ids = {f"r{j + 1}": r.review_id for j, r in enumerate(rows)}
    body = "\n".join(f"{k}: {r.text[:TRUNC]}" for k, r in zip(ids, rows))
    out = chat_json([
        {"role": "system", "content": "You classify Groww app reviews that mention fees or money words."},
        {"role": "user", "content": (
            f"For each review give stance and fee_type.\nstance options:\n{STANCE_HELP}\n\n"
            f"fee_type options: {FEE_HELP}\n\n"
            'Return JSON: {"labels":{"r1":{"stance":"confused","fee_type":"dp_charges"}}}\n\nReviews:\n' + body)}])
    res = {}
    for k, rid in ids.items():
        v = out.get("labels", {}).get(k, {})
        stance = v.get("stance") if v.get("stance") in STANCES else "unrelated"
        fee = v.get("fee_type") if v.get("fee_type") in FEE_TYPES else "none"
        res[rid] = {"stance": stance, "fee_type": fee}
    return res


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    df = pd.read_csv(SAMPLE)
    df["kw"] = df.text.map(matched_keywords)
    fee = df[df.kw.str.len() > 0].copy()
    print(f"reviews analysed ({SAMPLE.name}): {len(df)} | keyword-matched fee candidates: {len(fee)}")

    labels, rows = {}, list(fee.itertuples())
    for i in range(0, len(rows), BATCH):
        labels.update(label(rows[i:i + BATCH]))
        print(f"  labelled {min(i + BATCH, len(rows))}/{len(rows)}", flush=True)
    fee["stance"] = fee.review_id.map(lambda r: labels[r]["stance"])
    fee["fee_type"] = fee.review_id.map(lambda r: labels[r]["fee_type"])
    fee.drop(columns="kw").to_csv(LABELS_CSV, index=False)

    stance_counts = Counter(fee.stance)
    print("\nSTANCE COUNTS (code-counted):")
    for s in STANCES:
        print(f"  {s:15} {stance_counts.get(s, 0)}")

    conf = fee[fee.stance == "confused"]
    conf_by_fee = Counter(conf.fee_type)
    all_by_fee = Counter(fee[fee.stance != "unrelated"].fee_type)
    print("\nfee_type          confused  all-non-unrelated")
    for ft in sorted(FEE_TYPES, key=lambda f: (-conf_by_fee.get(f, 0), -all_by_fee.get(f, 0), f)):
        if conf_by_fee.get(ft) or all_by_fee.get(ft):
            print(f"  {ft:16}{conf_by_fee.get(ft, 0):>8}{all_by_fee.get(ft, 0):>12}")

    cands = [f for f in conf_by_fee if f not in IGNORED]
    issue = None
    if cands:
        issue = sorted(cands, key=lambda f: (-conf_by_fee[f], -all_by_fee.get(f, 0), f))[0]
    print(f"\nFEE ISSUE: {issue}" + (f"  ({conf_by_fee[issue]} confused reviews of {len(conf)} confused total)"
                                    if issue else "  (no confused reviews -> needs human decision)"))

    print("\nConfused reviews for the chosen fee (verify by eye):")
    for r in conf[conf.fee_type == issue].head(8).itertuples():
        print(f"  [{r.review_id[:8]} | {r.rating}*] {r.text[:200]}")

    OUT.write_text(json.dumps({
        "fee_issue": issue,
        "keyword_candidates": len(fee),
        "stance_counts": {s: stance_counts.get(s, 0) for s in STANCES},
        "confused_by_fee": dict(conf_by_fee),
        "all_by_fee": dict(all_by_fee),
        "confused_review_ids": conf[conf.fee_type == issue].review_id.tolist() if issue else [],
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
