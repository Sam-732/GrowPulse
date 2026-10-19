"""GrowPulse overview. Reads saved outputs only: no scraping, no Groq calls."""
import asyncio

import streamlit as st

import _boot as b

b.page("Overview", "◆")

summary = b.load_json("outputs/run_summary.json")
themes = b.load_json("outputs/themes.json")
fee = b.load_json("outputs/fee_issue.json")

b.hero("GrowPulse", "A weekly product pulse built from Play Store reviews, with a fact-checked fee explainer "
                    "and a human approval step before anything is published.")

if not (summary and themes and fee):
    b.need("outputs/run_summary.json", "outputs/themes.json", "outputs/fee_issue.json")
    b.footer()
    st.stop()

from src import history  # noqa: E402  (after _boot has set the path)

top = themes["themes"][0]
issue = fee["fee_issue"]
conf = fee["stance_counts"]["confused"]
state = history.overall()
last = state["last"]

# ---- MCP connection: only on request, never on page load
if "mcp" not in st.session_state:
    st.session_state.mcp = None


def check_mcp() -> dict:
    from src.mcp_tools import McpConfigError, open_session

    async def go():
        async with asyncio.timeout(25):
            async with open_session() as s:
                return sorted(t.name for t in (await s.list_tools()).tools)
    try:
        names = asyncio.run(go())
        ok = set(names) == {"append_to_doc", "read_doc", "create_email_draft"} and not any("send" in n for n in names)
        return {"ok": ok, "tools": names}
    except McpConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}"}


m = st.session_state.mcp
mcp_pill = ("Not checked", "muted") if m is None else (("Connected", "ok") if m["ok"] else ("Not connected", "bad"))
mcp_sub = "3 tools, no send tool" if m and m["ok"] else (m.get("error", "") if m else "Press the button below")

pub_sub = (f"Last run {last['started'].replace('T', ' ')}" if last else "No approval run yet")
b.grid([
    b.card("Reviews analysed", f"{summary['sample']:,}",
           f"sampled from {summary['clean']:,} clean ({summary['raw_fetched']:,} fetched)", "indigo"),
    b.card("Top issue", top["name"], f"{top['low_star']} of {top['total']} reviews are 1-2 star "
                                    f"({top['low_share']:.0%})", "accent"),
    b.card("Fee confusion", issue.replace("_", " ").title(),
           f"{fee['confused_by_fee'][issue]} of {conf} confused fee reviews; {fee['keyword_candidates']} fee-related",
           "accent"),
    b.card("Last publish", state["label"], pub_sub, pill=(("Doc " + ("done" if state["doc"] else "no") + " / Draft "
                                                           + ("done" if state["draft"] else "no")), state["tone"])),
    b.card("MCP server", mcp_pill[0], mcp_sub, pill=mcp_pill),
])

if st.button("Check MCP connection", help="Opens one short connection to the n8n server and lists its tools."):
    with st.spinner("Connecting to n8n..."):
        st.session_state.mcp = check_mcp()
    st.rerun()

st.subheader("Where the pain is")
mx = max((t["low_star"] for t in themes["themes"]), default=1) or 1
rows = []
for t in themes["themes"]:
    w = int(100 * t["low_star"] / mx)
    mark = "" if t["id"] in themes["top"] else " <span class='gp-pill muted'>not in top 3</span>"
    rows.append(f"<div style='margin:.55rem 0'><div class='gp-row'><span>{t['rank']}. {b.esc(t['name'])}{mark}</span>"
                f"<span><b>{t['low_star']}</b> low-star of {t['total']}</span></div>"
                f"<div class='gp-bar'><i style='width:{w}%'></i></div></div>")
st.markdown("".join(rows), unsafe_allow_html=True)
st.caption("Ranked by the number of 1-2 star reviews, not theme size. The tie-break rule is in themes.py.")

st.subheader("How to read this")
st.markdown(
    f"<div class='gp-note'>Data window: <b>{summary['weeks']} weeks</b> ({summary['first_week']} to "
    f"{summary['date_max']}). Counts are computed by code; the AI only sorts reviews into themes and labels fee "
    f"mentions. The fee signal is small: {fee['confused_by_fee'][issue]} of {conf} confused reviews name "
    f"{issue.replace('_', ' ')}, and {fee['confused_by_fee'].get('other', 0)} more name no specific fee. "
    f"Treat it as the best-supported guess, not a measured majority.</div>", unsafe_allow_html=True)

st.markdown("Use the sidebar: **Insights**, **Pulse**, **Fee explainer**, **Approve & publish**, **History**, **Checks**.")
b.footer()
