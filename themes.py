"""Phase 2: themes -> assignments -> ranking -> quotes.   AI sorts, code counts.

RANKING RULE (fixed before the first run):
  1. Rank themes by the number of 1-2 star reviews in the theme (descending).
  2. Tie-break A: higher share of 1-2 star reviews within the theme wins.
  3. Tie-break B: larger total review count wins.
  4. Tie-break C: theme name, alphabetical (deterministic).
UNASSIGNED reviews (bad/missing LLM label) are counted but never ranked.
"""
import json
import sys
from pathlib import Path

import pandas as pd

from src.llm import chat_json

SAMPLE = Path("data/reviews_sample.csv")
OUT = Path("outputs/themes.json")
ASSIGN = Path("data/theme_assignments.csv")
MAX_THEMES, TOP_N, BATCH, TRUNC, SEED = 5, 3, 25, 220, 42


def short(t: str, n: int = TRUNC) -> str:
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "..."


def discover_themes(df: pd.DataFrame) -> list[dict]:
    low, mid, high = (df[df.rating <= 2], df[df.rating == 3], df[df.rating >= 4])
    s = pd.concat([low.sample(min(60, len(low)), random_state=SEED),
                   mid.sample(min(30, len(mid)), random_state=SEED),
                   high.sample(min(60, len(high)), random_state=SEED)])
    lines = "\n".join(f"- ({r.rating} stars) {short(r.text)}" for r in s.itertuples())
    themes = []
    for attempt in range(3):
        out = chat_json([
            {"role": "system", "content": "You analyse Play Store reviews of the Groww investing app."},
            {"role": "user", "content": (
                f"Here are {len(s)} reviews. Propose AT MOST {MAX_THEMES} distinct themes that cover them "
                "(include praise as a theme if it is common). Return JSON: "
                '{"themes":[{"name":"<3-6 words>","description":"<one sentence>"}]}\n\n' + lines)}],
            nocache_salt=str(attempt))
        themes = out.get("themes", [])
        if 1 <= len(themes) <= MAX_THEMES:
            break
    themes = themes[:MAX_THEMES]               # code enforces the limit regardless
    return [{"id": f"T{i + 1}", "name": t["name"], "description": t.get("description", "")}
            for i, t in enumerate(themes)]


def assign(df: pd.DataFrame, themes: list[dict]) -> dict[str, str]:
    menu = "\n".join(f"{t['id']}: {t['name']} - {t['description']}" for t in themes)
    valid, result = {t["id"] for t in themes}, {}
    rows = list(df.itertuples())
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        ids = {f"r{j + 1}": r.review_id for j, r in enumerate(chunk)}   # short ids
        body = "\n".join(f"{k}: {short(r.text)}" for k, r in zip(ids, chunk))
        out = chat_json([
            {"role": "system", "content": "You label app reviews with exactly one theme id."},
            {"role": "user", "content": f"Themes:\n{menu}\n\nFor each review pick the single best theme id. "
             'Return JSON: {"labels":{"r1":"T2","r2":"T1"}}\n\nReviews:\n' + body}])
        labels = out.get("labels", {})
        for k, rid in ids.items():
            lab = labels.get(k)
            result[rid] = lab if lab in valid else "UNASSIGNED"
        print(f"  classified {min(i + BATCH, len(rows))}/{len(rows)}", flush=True)
    return result


def rank(df: pd.DataFrame, themes: list[dict]) -> list[dict]:
    stats = []
    for t in themes:
        g = df[df.theme == t["id"]]
        low = int((g.rating <= 2).sum())
        stats.append({**t, "total": len(g), "low_star": low,
                      "low_share": (low / len(g)) if len(g) else 0.0})
    stats.sort(key=lambda s: (-s["low_star"], -s["low_share"], -s["total"], s["name"]))
    for n, s in enumerate(stats, 1):
        s["rank"] = n
    return stats


def pick_quote(df: pd.DataFrame, theme: dict) -> dict | None:
    pool = df[(df.theme == theme["id"]) & (df.rating <= 2)]
    pool = pool[pool.text.str.split().str.len().between(10, 60)]
    pool = pool.sort_values(["thumbs_up", "date"], ascending=False).head(15)
    if pool.empty:
        return None
    cand = {f"c{j + 1}": r for j, r in enumerate(pool.itertuples())}
    body = "\n".join(f"{k}: {r.text}" for k, r in cand.items())
    out = chat_json([
        {"role": "system", "content": "You pick the most useful customer quote. Never rewrite text."},
        {"role": "user", "content": (
            f"Theme: {theme['name']} - {theme['description']}\nPick the ONE review that best illustrates "
            'the theme. Return JSON: {"id":"c3","substring":"<an exact 10-25 word stretch copied '
            'character-for-character from that review>"}\n\n' + body)}])
    row = cand.get(out.get("id"))
    if row is None:
        row = next(iter(cand.values()))
    sub = (out.get("substring") or "").strip()
    verified = bool(sub) and sub in row.text          # code verifies, char for char
    return {"review_id": row.review_id, "quote": sub if verified else row.text,
            "substring_verified": verified, "rating": int(row.rating), "date": row.date}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    df = pd.read_csv(SAMPLE)
    themes = discover_themes(df)
    print("THEMES:")
    for t in themes:
        print(f"  {t['id']} {t['name']} - {t['description']}")
    labels = assign(df, themes)
    df["theme"] = df.review_id.map(labels)
    df[["review_id", "theme"]].to_csv(ASSIGN, index=False)

    stats = rank(df, themes)
    print(f"\nUNASSIGNED: {(df.theme == 'UNASSIGNED').sum()} of {len(df)}")
    print(f"\n{'rank':<5}{'theme':<34}{'total':>6}{'1-2 star':>9}{'share':>8}")
    for s in stats:
        print(f"{s['rank']:<5}{s['name'][:32]:<34}{s['total']:>6}{s['low_star']:>9}{s['low_share']:>8.0%}")

    top = stats[:TOP_N]
    for s in top:
        s["quote"] = pick_quote(df, s)
        q = s["quote"]
        if q:
            tag = "PASS" if q["substring_verified"] else "fallback-full-text"
            print(f"\nTOP {s['rank']}: {s['name']}  [{q['review_id']} | {q['rating']} stars | "
                  f"{q['date']} | verbatim-check={tag}]\n  \"{q['quote']}\"")
    OUT.write_text(json.dumps({"themes": stats, "top": [s["id"] for s in top]},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
