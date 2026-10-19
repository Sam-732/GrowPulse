"""Themes ranked by 1-2 star count, with trend arrows and the real reviews behind each theme."""
import re

import pandas as pd
import streamlit as st

import _boot as b

b.page("Insights", "▲")
b.hero("Insights", "Five themes, ranked by how many 1-2 star reviews sit in each. Pick a theme to read the "
                   "actual reviews behind the number.")

themes = b.load_json("outputs/themes.json")
if not (themes and b.need("data/reviews_sample.csv", "data/theme_assignments.csv", "outputs/themes.json")):
    st.stop()

from src import metrics  # noqa: E402


@st.cache_data(show_spinner=False)
def load() -> pd.DataFrame:
    return metrics.theme_reviews()


df = load()
ranked = themes["themes"]
by_id = {t["id"]: t for t in ranked}
ARROW = {"up": ("▲", "bad", "worse"), "down": ("▼", "ok", "better"), "flat": ("▬", "muted", "flat")}

rows = []
for t in ranked:
    tr = metrics.trend(df, t["id"])
    sym, tone, word = ARROW[tr["direction"]]
    pct = f" ({tr['pct']:+.0f}%)" if tr["pct"] is not None else ""
    top = "<span class='gp-pill muted'>top 3</span>" if t["id"] in themes["top"] else ""
    rows.append(
        f"<div class='gp-card' style='margin-bottom:.6rem'><div class='gp-row'><span><b>{t['rank']}. {b.esc(t['name'])}</b> {top}</span>"
        f"<span class='gp-pill {tone}'>{sym} {tr['prev']} → {tr['recent']}{b.esc(pct)}</span></div>"
        f"<div class='s' style='color:#6B6578;font-size:.85rem;margin-top:.2rem'>{t['low_star']} of {t['total']} reviews are 1-2 star "
        f"({t['low_share']:.0%}) · trend: last 4 weeks vs the 4 before ({word})</div></div>")
st.markdown("".join(rows), unsafe_allow_html=True)
st.caption("▲ means more 1-2 star reviews recently (worse). Counts come from the 150-reviews-per-week sample, so "
           "small differences are noise.")

st.subheader("Read the reviews")
pick = st.pills("Theme", [t["id"] for t in ranked], selection_mode="single", default=ranked[0]["id"],
                format_func=lambda i: f"{by_id[i]['rank']}. {by_id[i]['name']}", label_visibility="collapsed")
pick = pick or ranked[0]["id"]
t = by_id[pick]
st.markdown(f"**{b.esc(t['name'])}**: {b.esc(t.get('description', ''))}")

q = t.get("quote")
if q:
    st.markdown(f"<div class='gp-quote'>“{b.esc(q['quote'])}”<br><small style='font-style:normal;color:#6B6578'>"
                f"Representative quote · {q['rating']}-star · {b.esc(q['date'])} · picked by the AI by ID, "
                f"text copied by code</small></div>", unsafe_allow_html=True)

st.bar_chart(metrics.weekly_low(df, pick).rename("1-2 star reviews"), color="#E4572E", height=170)

c1, c2, c3 = st.columns([2, 1.3, 1.3])
query = c1.text_input("Search these reviews", placeholder="e.g. brokerage, support, lag")
ratings = c2.multiselect("Stars", [1, 2, 3, 4, 5], default=[1, 2])
order = c3.selectbox("Sort", ["Newest", "Most helpful", "Lowest rating"])

view = df[(df.theme == pick) & (df.rating.isin(ratings))]
if query.strip():
    view = view[view.text.str.contains(re.escape(query.strip()), case=False, regex=True)]
view = {"Newest": view.sort_values(["date", "thumbs_up"], ascending=False),
        "Most helpful": view.sort_values(["thumbs_up", "date"], ascending=False),
        "Lowest rating": view.sort_values(["rating", "date"], ascending=[True, False])}[order]

PAGE = 20
key = f"shown_{pick}_{query}_{tuple(ratings)}_{order}"
shown = st.session_state.get(key, PAGE)
st.caption(f"Showing {min(shown, len(view))} of {len(view)} matching reviews "
           f"({int(((df.theme == pick)).sum())} in this theme in the sample)")
if view.empty:
    st.info("No reviews match. Try other stars or clear the search.")


def highlight(text: str, term: str) -> str:
    if not term.strip():
        return b.esc(text)
    parts = re.split(f"({re.escape(term.strip())})", text, flags=re.I)
    return "".join(f"<mark>{b.esc(p)}</mark>" if i % 2 else b.esc(p) for i, p in enumerate(parts))


for r in view.head(shown).itertuples():
    tone = "bad" if r.rating <= 2 else ("warn" if r.rating == 3 else "ok")
    st.markdown(
        f"<div class='gp-card' style='margin-bottom:.5rem'><div class='gp-row'><span class='gp-pill {tone}'>{'★' * int(r.rating)}"
        f"{'☆' * (5 - int(r.rating))}</span><span style='color:#6B6578;font-size:.8rem'>{b.esc(r.date)} · 👍 {int(r.thumbs_up)}</span></div>"
        f"<div style='margin-top:.4rem'>{highlight(r.text, query)}</div></div>", unsafe_allow_html=True)
if shown < len(view) and st.button(f"Show {min(PAGE, len(view) - shown)} more"):
    st.session_state[key] = shown + PAGE
    st.rerun()
b.footer()
