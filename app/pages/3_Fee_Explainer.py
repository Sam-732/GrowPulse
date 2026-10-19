"""Fee explainer: each bullet with its cited source and its check results, plus the label counts behind the fee issue."""
import pandas as pd
import streamlit as st

import _boot as b

b.page("Fee explainer", "₹")
b.hero("Fee explainer", "Neutral, facts-only bullets a support agent can send. Every fact comes from Groww's own "
                        "pages; every number is checked by code, and a second AI call acts as judge.")

ex = b.load_json("outputs/fee_explainer.json")
fee = b.load_json("outputs/fee_issue.json")
sources = b.load_json("data/sources.json")
if not (ex and fee and sources and b.need("outputs/fee_explainer.json", "outputs/fee_issue.json", "data/sources.json")):
    st.stop()

from src import factcheck  # noqa: E402

src = {s["id"]: s for s in sources}
audit = {a["final"]: a for a in ex.get("audit", []) if a.get("final")}
issue = fee["fee_issue"]
sc = fee["stance_counts"]

st.subheader(f"Why this topic: {issue.replace('_', ' ')}")
b.grid([
    b.card("Confused", str(sc["confused"]), "do not understand what they were charged", "accent"),
    b.card("Complaint only", str(sc["complaint_only"]), "understand it; think it is too much"),
    b.card("Praise", str(sc["praise"]), "think the charges are reasonable"),
    b.card("Unrelated", str(sc["unrelated"]), f"of {fee['keyword_candidates']} fee-keyword reviews"),
])
st.caption("Labels come from the AI; the counts are added up by code. A confused customer needs a clearer explanation; "
           "a complaint-only customer needs a pricing conversation, which no FAQ fixes.")
cb = pd.Series(fee["confused_by_fee"]).sort_values(ascending=False)
c1, c2 = st.columns([1.4, 1])
with c1:
    st.markdown("**Which fee are the 'confused' reviews about?**")
    st.bar_chart(cb.rename("confused reviews"), color="#3D348B", height=210)
with c2:
    st.markdown(
        f"<div class='gp-note'><b>Selection rule:</b> the specific fee with the most 'confused' reviews, ignoring "
        f"'other' and 'none'. <b>{b.esc(issue.replace('_', ' ').title())}</b> has {fee['confused_by_fee'][issue]}. "
        f"{fee['confused_by_fee'].get('other', 0)} confused reviews name no specific fee, so treat this as the "
        f"best-supported guess.</div>", unsafe_allow_html=True)

st.subheader("The explainer")
if ex.get("needs_human_review"):
    st.error("NEEDS HUMAN REVIEW: fewer than 3 bullets passed the checks. Do not publish.")
else:
    st.success(f"{len(ex['bullets'])} bullets passed. {ex.get('dropped', 0)} dropped.")

for i, bl in enumerate(ex["bullets"], 1):
    s = src.get(bl["source"], {})
    a = audit.get(bl["text"])
    judge = next((c for c in (a or {}).get("checks", []) if c["stage"] == "judge"), None)
    pills = []
    if judge:
        pills.append((f"judge: {judge['result'].lower()}", "ok" if judge["result"] == "PASS" else "bad"))
    try:
        n_ok = factcheck.numbers_in_source(bl["text"], bl["source"])
        e_ok = factcheck.evidence_verbatim(bl.get("evidence", []), bl["source"])
    except OSError:
        n_ok = e_ok = False
    pills.append(("numbers found in source" if n_ok else "number NOT in source", "ok" if n_ok else "bad"))
    pills.append(("evidence is verbatim" if e_ok else "evidence NOT verbatim", "ok" if e_ok else "bad"))
    if a and a.get("regenerated"):
        pills.append(("regenerated once", "warn"))
    pill_html = " ".join(f"<span class='gp-pill {t}'>{b.esc(x)}</span>" for x, t in pills)
    link = f"<a href='{b.esc(s.get('url', '#'))}' target='_blank'>{b.esc(s.get('title', bl['source']))}</a>"
    st.markdown(f"<div class='gp-card' style='margin-bottom:.6rem'><div><b>{i}.</b> {b.esc(bl['text'])}</div>"
                f"<div class='s' style='margin-top:.45rem'>Source: {link}</div><div style='margin-top:.4rem'>{pill_html}</div></div>",
                unsafe_allow_html=True)
    with st.expander("Evidence and checks"):
        for e in bl.get("evidence", []) if isinstance(bl.get("evidence"), list) else [bl.get("evidence", "")]:
            st.markdown(f"> {e}")
        if a:
            if a.get("regenerated"):
                first = a["checks"][0]
                st.caption(f"First draft: “{a['draft']}” was rejected by the {first['stage']} check "
                           f"({first['reason'] or first['result']}) and rewritten once.")
            for c in a["checks"]:
                st.caption(f"{c['stage']}: {c['result']}" + (f" ({c['reason']})" if c["reason"] else ""))
        st.caption(f"Judge model: {ex.get('judge_model', 'n/a')}")

st.subheader("Sources")
links = ex["source_links"]
for l in links:
    st.markdown(f"- [{l['title']}]({l['url']})")
st.markdown(f"**Last checked:** {ex['last_checked']}")
others = [s for s in sources if s["url"] not in {l["url"] for l in links}]
if others:
    with st.expander("Other official pages fetched (cross-check only)"):
        for s in others:
            st.markdown(f"- [{s['title']}]({s['url']})")
st.caption("Source links are hardcoded from the pages the pipeline fetched; the AI never writes a URL.")
b.footer()
