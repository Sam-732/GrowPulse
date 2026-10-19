"""Validation results from validate.py (no AI). The page reads the saved results; it does not re-run anything."""
import pandas as pd
import streamlit as st

import _boot as b

b.page("Checks", "✔")
b.hero("Checks", "Plain-rule checks, no AI: recounts, limits, verbatim quotes, source numbers, and safety. Each one is "
                 "independent, so one failure never hides another.")

res = b.load_json("outputs/validation_results.json")
if not res:
    st.info("No validation results yet. Run `python validate.py` and refresh.")
    b.footer()
    st.stop()

checks = res["checks"]
failed = [c for c in checks if not c["ok"]]
b.grid([
    b.card("Passed", f"{res['passed']} of {res['total']}", "checks passed", "accent" if failed else "indigo",
           pill=("all pass", "ok") if not failed else (f"{len(failed)} failing", "bad")),
    b.card("Last run", res["generated"].replace("T", " "), "saved by validate.py"),
    b.card("Areas", str(len({c['area'] for c in checks})), "data, themes, quotes, fee, pulse, explainer, safety, bad inputs"),
])
st.progress(res["passed"] / res["total"])

if failed:
    st.error("Failing checks: " + "; ".join(f"{c['area']}: {c['name']}" for c in failed))

only_failed = st.toggle("Show only failures", value=False, disabled=not failed)
areas = []
for c in checks:
    if c["area"] not in areas:
        areas.append(c["area"])

for area in areas:
    rows = [c for c in checks if c["area"] == area and (not only_failed or not c["ok"])]
    if not rows:
        continue
    ok_n = sum(c["ok"] for c in rows)
    with st.expander(f"{area}  ·  {ok_n}/{len(rows)} pass", expanded=bool([c for c in rows if not c["ok"]])):
        for c in rows:
            pill = "<span class='gp-pill ok'>PASS</span>" if c["ok"] else "<span class='gp-pill bad'>FAIL</span>"
            detail = (f"<div style='color:#6B6578;font-size:.8rem;margin:.1rem 0 .5rem 3.4rem'>{b.esc(c['detail'])}</div>"
                      if c["detail"] else "")
            st.markdown(f"<div>{pill} &nbsp;{b.esc(c['name'])}</div>{detail}", unsafe_allow_html=True)

with st.expander("Table view and download"):
    df = pd.DataFrame(checks).assign(result=lambda d: d.ok.map({True: "PASS", False: "FAIL"}))[["area", "name", "result", "detail"]]
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("Download validation_results.json", (b.ROOT / "outputs/validation_results.json").read_text(encoding="utf-8"),
                       file_name="validation_results.json", mime="application/json")
st.caption("To refresh: run `python validate.py` locally (it also checks the live MCP server) and commit the updated "
           "outputs/validation_results.json.")
b.footer()
