"""The weekly pulse, rendered from outputs/weekly_pulse.md (no regeneration, no AI call)."""
import re

import pandas as pd
import streamlit as st

import _boot as b

b.page("Weekly pulse", "✎")
b.hero("Weekly pulse", "One minute for a PM. The structure and every number come from code; the AI only wrote the "
                       "short sentences and the three action ideas.")

if not b.need("outputs/weekly_pulse.md", "outputs/pulse_parts.json", "data/reviews_sample.csv"):
    st.stop()

text = (b.ROOT / "outputs/weekly_pulse.md").read_text(encoding="utf-8")
meta = b.load_json("outputs/pulse_parts.json")
LIMIT = 250
n_words = len(text.split())            # same strict count as pulse.py: every whitespace token

# ---- parse the saved markdown into parts (falls back to raw markdown if the shape changes)
title = re.search(r"^# (.+)$", text, re.M)
sub = re.search(r"^# .+\n(.+)$", text, re.M)
theme_blocks = re.findall(r'^(\d)\. \*\*(.+?)\*\*: (.+?)\n> "(.*)" \((\d)-star, ([\d-]+)\)', text, re.M)
obs = re.search(r"## Key observation\n(.+?)\n\n", text, re.S)
fee = re.search(r"## Fee watch\n(.+?)\n\n", text, re.S)
actions = re.findall(r"^\d\. (.+)$", text.split("## Actions")[1], re.M) if "## Actions" in text else []

sample = pd.read_csv(b.ROOT / "data/reviews_sample.csv")
review_texts = sample.text.tolist()
quotes_ok = bool(theme_blocks) and all(any(q[3] in t for t in review_texts) for q in theme_blocks)
live = {"3 themes": len(theme_blocks) == 3, "quotes found in CSV": quotes_ok, "3 actions": len(actions) == 3,
        f"within {LIMIT} words": n_words <= LIMIT}
ok_status = all(live.values())
b.grid([
    b.card("Pulse", (title.group(1) if title else "Weekly Product Pulse").replace("Weekly Product Pulse - ", ""),
           sub.group(1) if sub else "", "indigo"),
    b.card("Word count", f"{n_words} of {LIMIT}", f"{LIMIT - n_words} to spare; counted by code, every token",
           "accent", pill=("within limit", "ok") if n_words <= LIMIT else ("over limit", "bad")),
    b.card("Live checks", "All passed" if ok_status else "Needs attention",
           ", ".join(f"{k}: {'yes' if v else 'NO'}" for k, v in live.items()),
           pill=("passed" if ok_status else "failed", "ok" if ok_status else "bad")),
])
st.progress(min(n_words / LIMIT, 1.0))

if not theme_blocks:
    st.markdown(text)
    b.footer()
    st.stop()

st.subheader("Top themes")
for rank, name, body, quote, stars, date in theme_blocks:
    head, _, sentence = body.partition(". ")
    verified = any(quote in t for t in review_texts)
    pill = ("quote verified in CSV", "ok") if verified else ("quote NOT found in CSV", "bad")
    st.markdown(
        f"<div class='gp-card accent' style='margin-bottom:.8rem'><div class='gp-row'><b>{rank}. {b.esc(name)}</b>"
        f"<span class='gp-pill {pill[1]}'>{pill[0]}</span></div>"
        f"<div style='color:#6B6578;font-size:.85rem;margin:.25rem 0'>{b.esc(head)}.</div>"
        f"<div style='margin:.3rem 0'>{b.esc(sentence)}</div>"
        f"<div class='gp-quote'>“{b.esc(quote)}”<br><small style='font-style:normal;color:#6B6578'>{stars}-star · {b.esc(date)}</small></div></div>",
        unsafe_allow_html=True)

left, right = st.columns(2)
with left:
    st.subheader("Key observation")
    st.markdown(f"<div class='gp-note'>{b.esc(obs.group(1).strip() if obs else '')}</div>", unsafe_allow_html=True)
with right:
    st.subheader("Fee watch")
    st.markdown(f"<div class='gp-note'>{b.esc((fee.group(1) if fee else '').replace('**', '').strip())}</div>",
                unsafe_allow_html=True)

st.subheader("Three actions")
for i, a in enumerate(actions, 1):
    st.markdown(f"<div class='gp-card' style='margin-bottom:.5rem'><div class='gp-row'><span><b>{i}.</b> {b.esc(a)}</span></div></div>",
                unsafe_allow_html=True)
if len(actions) != 3:
    st.warning(f"Expected exactly 3 actions, found {len(actions)}.")

with st.expander("Raw markdown and download"):
    st.code(text, language="markdown")
    st.download_button("Download weekly_pulse.md", text, file_name="weekly_pulse.md", mime="text/markdown")
b.footer()
