"""History of approval runs, read from logs/approve_*.jsonl. Read-only."""
import pandas as pd
import streamlit as st

import _boot as b

b.page("History", "⟲")
b.hero("History", "Every approval attempt, rejected or published, with each step and its result.")

from src import history  # noqa: E402

runs = history.runs()
state = history.overall()
if not runs:
    st.info("No approval runs yet. Use **Approve & publish** (or `python approve.py`) and the run will appear here.")
    b.footer()
    st.stop()

TONE = {"Published": "ok", "Rejected": "muted", "Partial": "warn", "Failed": "bad", "Approved": "warn"}


def tone(outcome: str) -> str:
    return next((v for k, v in TONE.items() if outcome.startswith(k)), "muted")


b.grid([
    b.card("Runs logged", str(len(runs)), "newest first", "indigo"),
    b.card("Overall", state["label"], "combined across runs (a resume can finish an earlier run)", "accent",
           pill=(state["label"], state["tone"])),
    b.card("Doc / Draft", f"{'✓' if state['doc'] else '–'} / {'✓' if state['draft'] else '–'}",
           "entry in the Doc / Gmail draft created"),
])

STATUS_TONE = {"ok": "ok", "APPROVED": "ok", "skipped": "muted", "REJECTED": "muted", "STOP": "warn", "WARN": "warn",
               "FAIL": "bad"}

for r in runs:
    pill = f"<span class='gp-pill {tone(r['outcome'])}'>{b.esc(r['outcome'])}</span>"
    st.markdown(f"<div class='gp-card' style='margin-bottom:.4rem'><div class='gp-row'><b>{b.esc(r['started'].replace('T', ' '))}</b>"
                f"{pill}</div><div class='s' style='font-size:.8rem;color:#6B6578;margin-top:.3rem'>"
                f"SHA-256 {b.esc(r['sha256'][:16])}… · {b.esc(r['file'])}</div></div>", unsafe_allow_html=True)
    with st.expander("Steps"):
        if r["reason"]:
            st.markdown(f"**Rejection reason:** {r['reason']}")
        if r["error"]:
            st.markdown(f"**Error:** `{r['error']}`")
        rows = [{"time": x["ts"].split("T")[1], "step": x["step"], "result": x["status"],
                 "detail": x.get("reason", "") or x.get("detail", "")} for x in r["steps"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption("History is read from the saved logs. On a hosted deployment the filesystem resets between restarts, so "
           "runs made on the live site survive only if the log files are committed.")
b.footer()
