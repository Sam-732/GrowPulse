"""Phase 8: no-AI validation. Plain rules, one PASS/FAIL per check, every check independent.
Writes outputs/validation_report.md. Exit code 1 if anything FAILs.   Usage: python validate.py
"""
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

OUT, DATA = Path("outputs"), Path("data")
REQUIRED_COLS = ["review_id", "text", "rating", "date", "week_start"]
PII_COLS = {"username", "user_name", "userName", "name", "email", "phone"}
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
NUM = re.compile(r"\d+(?:[.,]\d+)*")

RESULTS: list[tuple[str, str, bool, str]] = []        # area, name, ok, detail


def check(area: str, name: str):
    def deco(fn):
        try:
            res = fn()
            ok, detail = (res if isinstance(res, tuple) else (bool(res), ""))
        except Exception as e:                        # noqa: BLE001 - a crashing check is a FAIL, not a stop
            ok, detail = False, f"check crashed: {type(e).__name__}: {e}"
        RESULTS.append((area, name, bool(ok), str(detail)))
        return fn
    return deco


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def words(t: str) -> int:
    return len(t.split())


def nums(t: str) -> set[str]:
    return {n.rstrip(".,").replace(",", "") for n in NUM.findall(t)}


def review_problems(df: pd.DataFrame) -> list[str]:
    """Pure rule-based validator for a reviews frame; used on real data and on bad inputs."""
    p = []
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        return [f"missing columns {missing}"]
    if len(df) == 0:
        return ["empty file"]
    if len(df) < 100:
        p.append(f"only {len(df)} rows (<100)")
    if PII_COLS & set(df.columns):
        p.append("PII column present")
    r = pd.to_numeric(df["rating"], errors="coerce")
    if r.isna().any() or not r.between(1, 5).all():
        p.append("ratings outside 1-5 or non-numeric")
    txt = df["text"].astype(str)
    if txt.map(lambda t: bool(PHONE.search(t) or EMAIL.search(t))).any():
        p.append("phone/email found in text")
    d = pd.to_datetime(df["date"], errors="coerce")
    if d.isna().any():
        p.append("unparseable dates")
    else:
        weeks = d.dt.to_period("W").nunique()
        if not 8 <= weeks <= 12:
            p.append(f"{weeks} weeks of data (need 8-12)")
    return p


sample = pd.read_csv(DATA / "reviews_sample.csv") if (DATA / "reviews_sample.csv").exists() else pd.DataFrame()

# ------------------------------------------------------------------ DATA
@check("Data", "required columns exist")
def _():
    miss = [c for c in REQUIRED_COLS if c not in sample.columns]
    return not miss, f"missing {miss}" if miss else f"{len(sample)} rows"

@check("Data", "no username/email/phone columns or values")
def _():
    bad = PII_COLS & set(sample.columns)
    n = int(sample["text"].astype(str).map(lambda t: bool(PHONE.search(t) or EMAIL.search(t))).sum())
    return not bad and n == 0, f"pii cols {sorted(bad)}, text hits {n}"

@check("Data", "span is 8-12 weeks")
def _():
    w = pd.to_datetime(sample["date"]).dt.to_period("W").nunique()
    return 8 <= w <= 12, f"{w} weeks"

@check("Data", "cap of 150 reviews per week respected")
def _():
    m = sample.groupby("week_start").size().max()
    return m <= 150, f"max {m}/week"

@check("Data", "ratings are all integers 1-5")
def _():
    return sample["rating"].between(1, 5).all() and (sample["rating"] % 1 == 0).all()

@check("Data", "review_id unique")
def _():
    return sample["review_id"].is_unique

# ------------------------------------------------------------------ THEMES
th = J(OUT / "themes.json")
asg = pd.read_csv(DATA / "theme_assignments.csv")
merged = sample.merge(asg, on="review_id")

@check("Themes", "at most 5 themes")
def _():
    return len(th["themes"]) <= 5, f"{len(th['themes'])} themes"

@check("Themes", "exactly 3 top themes")
def _():
    return len(th["top"]) == 3, f"{len(th['top'])}"

@check("Themes", "counts match a from-scratch recount")
def _():
    bad = []
    for t in th["themes"]:
        g = merged[merged.theme == t["id"]]
        if len(g) != t["total"] or int((g.rating <= 2).sum()) != t["low_star"]:
            bad.append(t["id"])
    return not bad, f"mismatched {bad}" if bad else "all theme totals and 1-2 star counts match"

@check("Themes", "every review has a theme and theme totals sum to the sample size")
def _():
    s = sum(t["total"] for t in th["themes"]) + int((merged.theme == "UNASSIGNED").sum())
    return s == len(sample) == len(merged), f"{s} vs {len(sample)}"

@check("Themes", "ranking follows the written rule (1-2 star desc, share desc, total desc, name)")
def _():
    exp = sorted(th["themes"], key=lambda s: (-s["low_star"], -s["low_share"], -s["total"], s["name"]))
    return [t["id"] for t in exp][:3] == th["top"], f"expected top {[t['id'] for t in exp][:3]}, got {th['top']}"

# ------------------------------------------------------------------ QUOTES
pulse = (OUT / "weekly_pulse.md").read_text(encoding="utf-8")
by_id = sample.set_index("review_id")["text"].to_dict()

@check("Quotes", "3 stored quotes are verbatim substrings of their CSV review")
def _():
    qs = [t["quote"] for t in th["themes"] if t["id"] in th["top"]]
    bad = [q["review_id"] for q in qs if q["review_id"] not in by_id or q["quote"] not in by_id[q["review_id"]]]
    return len(qs) == 3 and not bad, f"bad {bad}"

@check("Quotes", "3 quotes in the pulse appear word for word in the CSV")
def _():
    quoted = re.findall(r'^> "(.*)" \(', pulse, flags=re.M)
    texts = list(by_id.values())
    miss = [q[:40] for q in quoted if not any(q in t for t in texts)]
    return len(quoted) == 3 and not miss, f"{len(quoted)} quotes, missing {miss}"

@check("Quotes", "each pulse quote is 10-25 words")
def _():
    quoted = re.findall(r'^> "(.*)" \(', pulse, flags=re.M)
    return all(10 <= words(q) <= 25 for q in quoted), str([words(q) for q in quoted])

# ------------------------------------------------------------------ FEE
fee = J(OUT / "fee_issue.json")
labels = pd.read_csv(DATA / "fee_labels.csv")

@check("Fee issue", "stance counts match a recount of data/fee_labels.csv")
def _():
    c = Counter(labels.stance)
    ok = all(c.get(k, 0) == v for k, v in fee["stance_counts"].items())
    return ok, str(dict(c))

@check("Fee issue", "fee issue = most frequent fee among 'confused' (ignoring other/none), tie-break per rule")
def _():
    conf = labels[labels.stance == "confused"]
    cb = Counter(conf.fee_type)
    allb = Counter(labels[labels.stance != "unrelated"].fee_type)
    cands = [f for f in cb if f not in {"other", "none"}]
    exp = sorted(cands, key=lambda f: (-cb[f], -allb.get(f, 0), f))[0] if cands else None
    return exp == fee["fee_issue"], f"expected {exp}, file says {fee['fee_issue']}"

@check("Fee issue", "all labels are from the allowed sets")
def _():
    ok = set(labels.stance) <= {"confused", "complaint_only", "praise", "unrelated"}
    return ok

# ------------------------------------------------------------------ PULSE
@check("Pulse", "at most 250 words")
def _():
    return words(pulse) <= 250, f"{words(pulse)} words"

@check("Pulse", "required sections present (themes, quotes, key observation, actions)")
def _():
    need = ["## Top themes", "## Key observation", "## Actions"]
    miss = [n for n in need if n not in pulse]
    return not miss and pulse.count('\n> "') == 3, f"missing {miss}, quotes {pulse.count(chr(10) + '> ' + chr(34))}"

@check("Pulse", "exactly 3 action ideas")
def _():
    acts = pulse.split("## Actions")[1] if "## Actions" in pulse else ""
    n = len(re.findall(r"^\d+\. ", acts, flags=re.M))
    return n == 3, f"{n}"

@check("Pulse", "theme numbers in the pulse equal recomputed counts")
def _():
    miss = []
    for t in (x for x in th["themes"] if x["id"] in th["top"]):
        if f"{t['low_star']} of {t['total']} are 1-2 star" not in pulse:
            miss.append(t["id"])
    return not miss, f"missing {miss}"

@check("Pulse", "fee numbers in the pulse equal fee_issue.json")
def _():
    i = fee["fee_issue"]
    return f"{fee['confused_by_fee'][i]} of {fee['stance_counts']['confused']} confused" in pulse

# ------------------------------------------------------------------ EXPLAINER
ex = J(OUT / "fee_explainer.json")
md = (OUT / "fee_explainer.md").read_text(encoding="utf-8")
src_meta = {m["id"]: m for m in J(DATA / "sources.json")}

def src_text(sid):
    t = (DATA / "sources" / f"{sid}.txt").read_text(encoding="utf-8")
    for m in ["Was the answer helpful?", "Vaishnavi Tech Park"]:
        i = t.find(m)
        t = t[:i] if i > 0 else t
    return t

@check("Explainer", "at most 6 bullets (and at least 3)")
def _():
    n = len(ex["bullets"])
    return 3 <= n <= 6, f"{n}"

@check("Explainer", "exactly 2 official source links, both from the fetched list")
def _():
    urls = [l["url"] for l in ex["source_links"]]
    official = {m["url"] for m in src_meta.values()}
    return len(urls) == 2 and set(urls) <= official and all(u.startswith("https://groww.in/") for u in urls), str(urls)

@check("Explainer", "'Last checked' date present")
def _():
    return bool(re.search(r"Last checked: \d{4}-\d{2}-\d{2}", md))

@check("Explainer", "every number in every bullet appears in its cited source")
def _():
    bad = []
    for b in ex["bullets"]:
        if nums(b["text"]) - nums(src_text(b["source"])):
            bad.append(b["text"][:50])
    return not bad, f"bad {bad}"

@check("Explainer", "no URLs written inside bullet text (links are hardcoded)")
def _():
    return not any(re.search(r"https?://|www\.", b["text"]) for b in ex["bullets"])

@check("Explainer", "no opinion words")
def _():
    rx = re.compile(r"\b(cheap|expensive|unfair|overpriced|reasonable|best|worst|hidden|scam|affordable|costly)\b", re.I)
    return not any(rx.search(b["text"]) for b in ex["bullets"])

@check("Explainer", "not marked NEEDS HUMAN REVIEW (>=3 bullets passed number check + judge)")
def _():
    return not ex["needs_human_review"] and "NEEDS HUMAN REVIEW" not in md, f"dropped {ex['dropped']}"

@check("Explainer", "explainer topic equals the identified fee issue")
def _():
    return ex["fee_issue"] == fee["fee_issue"]

# ------------------------------------------------------------------ SAFETY
import approve  # noqa: E402  (builds the text only; no MCP calls on import)

@check("Safety", "approval fingerprint is stable across two independent builds")
def _():
    a, b = approve.build(), approve.build()
    return a["hash"] == b["hash"], a["hash"][:16]

@check("Safety", "email subject has the required format")
def _():
    s = approve.build()["subject"]
    return bool(re.fullmatch(r"Weekly Product Pulse \+ Customer Clarification — \d{4}-\d{2}-\d{2}", s)), s

@check("Safety", "doc entry contains all 6 required fields")
def _():
    e = approve.build()["doc_entry"]
    need = ["date:", "top_themes:", "weekly_pulse:", "identified_fee_issue:", "explanation_bullets:", "source_links:"]
    miss = [n for n in need if n not in e]
    return not miss, f"missing {miss}"

@check("Safety", "approve.py requires the exact string APPROVE")
def _():
    src = Path("approve.py").read_text(encoding="utf-8")
    return 'answer != "APPROVE"' in src

@check("Safety", "no 'send' tool exists on the MCP server (live) and tool set is exactly 3")
def _():
    from src.mcp_tools import open_session

    async def go():
        async with open_session() as s:
            return {t.name: t for t in (await s.list_tools()).tools}
    tools = asyncio.run(go())
    ok = set(tools) == {"append_to_doc", "read_doc", "create_email_draft"} and not any("send" in n for n in tools)
    return ok, str(sorted(tools))

@check("Safety", "append_to_doc is configured to insert (not 'Old_Text' replace)")
def _():
    from src.mcp_tools import open_session

    async def go():
        async with open_session() as s:
            return {t.name: t for t in (await s.list_tools()).tools}
    props = list(asyncio.run(go())["append_to_doc"].input_schema.get("properties", {}))
    return not any("old_text" in p.lower() for p in props), f"params {props}"

@check("Safety", ".env, venv/, cache/ are git-ignored and .env is not tracked")
def _():
    gi = Path(".gitignore").read_text(encoding="utf-8")
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
    return all(x in gi for x in (".env", "venv/", "cache/")) and ".env" not in tracked, ""

@check("Safety", "no API key or MCP token in any tracked/working source file")
def _():
    secret_rx = re.compile(r"gsk_[A-Za-z0-9]{20,}")
    token = ""
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("N8N_MCP_TOKEN="):
            token = line.split("=", 1)[1].strip()
    hits = []
    for p in list(Path(".").glob("*.py")) + list(Path("src").glob("*.py")) + list(Path(".").glob("*.md")) \
            + list(Path("outputs").glob("*")) + list(Path("docs").glob("*")):
        t = p.read_text(encoding="utf-8", errors="ignore")
        if secret_rx.search(t) or (token and token in t):
            hits.append(str(p))
    return not hits, f"hits {hits}"

@check("Safety", "LLM responses are cached (cache/ non-empty)")
def _():
    n = len(list(Path("cache").glob("*.json")))
    return n > 0, f"{n} cached responses"

# ------------------------------------------------------------------ BAD INPUTS (validator must reject each)
def _frame(n=300, weeks=12, **over):
    dates = pd.date_range("2026-07-27", periods=weeks * 7, freq="D")
    df = pd.DataFrame({"review_id": [f"r{i}" for i in range(n)], "text": ["good app works well for me"] * n,
                       "rating": [4] * n, "date": [dates[i % len(dates)].strftime("%Y-%m-%d") for i in range(n)],
                       "week_start": ["x"] * n})
    for k, v in over.items():
        df[k] = v
    return df

BAD = {
    "empty file": pd.DataFrame(),
    "missing column": _frame().drop(columns=["rating"]),
    "only 20 rows": _frame(n=20),
    "rating 0": _frame(rating=[0] * 300),
    "rating 'good'": _frame(rating=["good"] * 300),
    "phone number in text": _frame(text=["call me on 9876543210 now please"] * 300),
    "20 weeks of data": _frame(weeks=20),
    "username column": _frame(username=["bob"] * 300),
}
for label, frame in BAD.items():
    @check("Bad inputs", f"validator rejects: {label}")
    def _(frame=frame):
        probs = review_problems(frame)
        return bool(probs), "; ".join(probs)

@check("Bad inputs", "validator accepts a clean frame")
def _():
    probs = review_problems(_frame())
    return not probs, "; ".join(probs)

@check("Bad inputs", "validator accepts the real sample")
def _():
    probs = review_problems(sample)
    return not probs, "; ".join(probs)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    lines, area = [], None
    for a, name, ok, detail in RESULTS:
        if a != area:
            area = a
            lines.append(f"\n[{a}]")
        lines.append(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   ({detail})" if detail and not ok else
                                                              f"   ({detail})" if detail else ""))
    passed = sum(ok for *_, ok, _ in RESULTS)
    summary = f"\n{passed}/{len(RESULTS)} checks passed"
    text = "\n".join(lines) + summary
    print(text)
    (OUT / "validation_report.md").write_text(f"# Validation report ({datetime.now():%Y-%m-%d %H:%M})\n```\n{text}\n```\n",
                                              encoding="utf-8")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
