"""Approve & publish. Calls the SAME functions as approve.py (build, Log, accept, reject, finish/publish).

Gates: APP_PASSWORD, then typing APPROVE (exact, capitals). Anything else is a rejection: reason asked, nothing written.
Nothing here is sent: the n8n server has no send tool, and the email is only ever a Gmail draft.
"""
import hmac
import os

import streamlit as st

import _boot as b

b.page("Approve & publish", "✓")
b.hero("Approve & publish", "You see the exact text first. Nothing is written until you sign in and type APPROVE. "
                            "The email is only ever saved as a draft.")

if not b.need("outputs/weekly_pulse.md", "outputs/fee_explainer.json", "outputs/pulse_parts.json",
              "outputs/fee_issue.json", "data/sources.json"):
    st.stop()

import approve  # noqa: E402  (the same module the terminal uses)
from src import history  # noqa: E402

PASSWORD = os.environ.get("APP_PASSWORD", "")
S = st.session_state
S.setdefault("authed", False)
S.setdefault("fails", 0)
S.setdefault("need_reason", False)
S.setdefault("result", None)

approved = approve.build()
state = history.overall()

# ---------------------------------------------------------------- the exact text and fingerprint
b.grid([
    b.card("Week entry", approved["entry_id"].replace("review-pulse-", "week of "), "one entry per week in the Doc", "indigo"),
    b.card("Doc entry", "In the Doc" if state["doc"] else "Not written", "from the approve logs",
           pill=("done", "ok") if state["doc"] else ("pending", "muted")),
    b.card("Gmail draft", "Created" if state["draft"] else "Not created", "never sent",
           pill=("done", "ok") if state["draft"] else ("pending", "warn")),
])
st.markdown(f"**SHA-256 of the exact text:** `{approved['hash']}`")
st.caption("This fingerprint covers the Doc entry, the email subject and the email body. It is re-checked before "
           "each write; if one character changes, publishing stops.")

t1, t2 = st.tabs(["Google Doc entry", "Gmail draft"])
with t1:
    st.code(approved["doc_entry"], language="text")
with t2:
    st.markdown(f"**Subject:** {approved['subject']}")
    st.code(approved["body"], language="text")

if approved["needs_review"]:
    st.error("BLOCKED: the pulse or the fee explainer is marked NEEDS HUMAN REVIEW or failed its limits.")
    st.stop()

# ---------------------------------------------------------------- gate 1: password
st.subheader("Sign in to publish")
if not PASSWORD:
    st.warning("Publishing is switched off: APP_PASSWORD is not configured for this deployment. "
               "Reading and previewing still work.")
    st.stop()
if S.fails >= 5:
    st.error("Too many wrong passwords in this session. Reload the page to try again.")
    st.stop()
if not S.authed:
    with st.form("login"):
        pw = st.text_input("App password", type="password")
        if st.form_submit_button("Unlock"):
            if hmac.compare_digest(pw.encode(), PASSWORD.encode()):
                S.authed = True
                S.fails = 0
                st.rerun()
            S.fails += 1
            st.error("Wrong password.")
    st.stop()
st.success("Unlocked for this session.")

# ---------------------------------------------------------------- finished: show the result, no second publish
STEPS = ["1 read_doc (duplicate check)", "2 re-check hash", "3 append_to_doc", "4 read_doc (verify)",
         "5 re-check hash", "6 create_email_draft"]


def render_steps(events: dict) -> str:
    out = []
    for name in STEPS:
        e = events.get(name[0])
        if e is None:
            mark, note = "·", "waiting"
        elif e["status"] == "ok":
            mark, note = "✅", "ok"
        elif e["status"] == "skipped":
            mark, note = "⏭️", "skipped (already in the doc, resuming)"
        elif e["status"] == "STOP":
            mark, note = "⏹️", "stopped: " + e.get("reason", "")
        else:
            mark, note = "❌", "FAILED"
        out.append(f"{mark} **{name}** · {note}")
    return "\n\n".join(out)


if S.result:
    ok, msg, events = S.result
    (st.success if ok else st.error)(msg)
    st.markdown(render_steps(events))
    st.caption("Reload the page to start a new session. The log is saved and appears under History.")
    st.stop()

# ---------------------------------------------------------------- gate 2: type APPROVE, or reject
st.subheader("Approve or reject")
typed = st.text_input("Type APPROVE (exact, capitals) to write the Doc entry and create the Gmail draft",
                      key="typed", autocomplete="off")
c1, c2 = st.columns(2)
publish_clicked = c1.button("Publish", type="primary", width="stretch")
reject_clicked = c2.button("Reject", width="stretch")

if publish_clicked and typed != "APPROVE":
    S.need_reason = True            # same rule as the terminal: anything else is a rejection
if reject_clicked:
    S.need_reason = True

if S.need_reason and not (publish_clicked and typed == "APPROVE"):
    st.info("Not approved. Tell us why; nothing will be written.")
    with st.form("reason"):
        reason = st.text_input("Reason for rejecting")
        if st.form_submit_button("Record rejection"):
            if not reason.strip():
                st.error("A reason is required.")
            else:
                approve.reject(approved, reason.strip(), approve.Log())
                S.need_reason = False
                S.result = (False, "Rejected. Nothing was written to the Doc or Gmail.", {})
                st.rerun()

if publish_clicked and typed == "APPROVE":
    S.need_reason = False
    events: dict = {}
    box = st.empty()

    def on_event(rec: dict) -> None:
        events[rec["step"][0]] = rec
        box.markdown(render_steps(events))

    log = approve.Log(on_event=on_event)
    approve.accept(approved, log)
    with st.spinner("Publishing. Each step is verified before the next one runs..."):
        ok, msg = approve.finish(approved, log)
    S.result = (ok, msg, events)
    st.rerun()
b.footer()
