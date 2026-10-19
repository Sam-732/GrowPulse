"""Shared app setup: paths, secrets -> environment, GrowPulse styling, small helpers.

Pages read saved files only. Nothing here scrapes or calls Groq.
"""
import html
import json
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)                     # approve.py and src/* use repo-relative paths

SECRET_KEYS = ("GROQ_API_KEY", "N8N_MCP_URL", "N8N_MCP_TOKEN", "APP_PASSWORD")


def load_secrets() -> None:
    """Streamlit Cloud secrets -> os.environ (locally, .env is loaded by src/mcp_tools)."""
    try:
        for k in SECRET_KEYS:
            if k in st.secrets:
                os.environ.setdefault(k, str(st.secrets[k]))
    except Exception:              # no secrets file locally: fine
        pass


load_secrets()

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500;600&display=swap');
:root{--ink:#1D1A2F;--paper:#F7F3EC;--sand:#EFE8DB;--line:#E0D7C6;--vermilion:#E4572E;--indigo:#3D348B;--muted:#6B6578;
--ok:#2F6F5E;--warn:#B7791F;--bad:#B3261E;}
html,body,[class*="css"]{font-family:'Inter',system-ui,sans-serif;}
h1,h2,h3{font-family:'Fraunces',Georgia,serif!important;color:var(--ink);letter-spacing:-0.01em;}
.block-container{padding-top:2rem;padding-bottom:4rem;max-width:1080px;}
[data-testid="stSidebar"]{background:var(--ink);}
[data-testid="stSidebar"] *{color:#F7F3EC!important;}
[data-testid="stSidebarNav"] a{border-radius:8px;}
.gp-brand{font-family:'Fraunces',serif;font-weight:700;font-size:1.5rem;letter-spacing:-0.02em;}
.gp-brand b{color:var(--vermilion);}
.gp-tag{font-size:.8rem;opacity:.75;margin-top:-.2rem;}
.gp-hero{padding:1.6rem 1.6rem 1.4rem;border-radius:18px;background:var(--ink);color:#F7F3EC;margin-bottom:1.2rem;
background-image:radial-gradient(circle at 92% 15%,rgba(228,87,46,.55),transparent 38%),radial-gradient(circle at 70% 120%,rgba(61,52,139,.7),transparent 45%);}
.gp-hero h1{color:#F7F3EC!important;margin:0 0 .2rem;font-size:2.3rem;}
.gp-hero p{margin:0;opacity:.85;max-width:46rem;}
.gp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:.8rem;margin:.4rem 0 1.2rem;}
.gp-card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:.95rem 1rem;box-shadow:0 1px 0 rgba(29,26,47,.04);}
.gp-card .l{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;}
.gp-card .v{font-family:'Fraunces',serif;font-size:1.55rem;line-height:1.15;margin:.25rem 0;font-weight:700;color:var(--ink);}
.gp-card .s{font-size:.82rem;color:var(--muted);}
.gp-card.accent{border-top:4px solid var(--vermilion);}
.gp-card.indigo{border-top:4px solid var(--indigo);}
.gp-pill{display:inline-block;padding:.12rem .55rem;border-radius:999px;font-size:.75rem;font-weight:600;}
.gp-pill.ok{background:#DDEEE8;color:var(--ok);} .gp-pill.warn{background:#F7E8C8;color:var(--warn);}
.gp-pill.bad{background:#F6D9D6;color:var(--bad);} .gp-pill.muted{background:var(--sand);color:var(--muted);}
.gp-bar{height:9px;border-radius:99px;background:var(--sand);overflow:hidden;margin-top:.35rem;}
.gp-bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--vermilion),#F0885F);border-radius:99px;}
.gp-row{display:flex;justify-content:space-between;gap:1rem;font-size:.95rem;}
.gp-note{border-left:4px solid var(--indigo);background:#fff;border-radius:10px;padding:.7rem .9rem;font-size:.88rem;color:var(--ink);border:1px solid var(--line);border-left-width:4px;}
.gp-quote{border-left:3px solid var(--vermilion);padding:.2rem .8rem;margin:.3rem 0 .9rem;color:#2c2842;font-style:italic;}
.gp-foot{color:var(--muted);font-size:.78rem;margin-top:2rem;}
@media (max-width:640px){.gp-hero h1{font-size:1.8rem;}.block-container{padding-left:1rem;padding-right:1rem;}}
</style>
"""


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def page(title: str, icon: str = "◆") -> None:
    """Call first on every page."""
    st.set_page_config(page_title=f"{title} · GrowPulse", page_icon=icon, layout="wide",
                       initial_sidebar_state="auto")
    st.markdown(CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("<div class='gp-brand'>Grow<b>Pulse</b></div><div class='gp-tag'>Weekly product pulse from app reviews</div>",
                    unsafe_allow_html=True)


def hero(title: str, text: str) -> None:
    st.markdown(f"<div class='gp-hero'><h1>{esc(title)}</h1><p>{esc(text)}</p></div>", unsafe_allow_html=True)


def card(label: str, value: str, sub: str = "", tone: str = "", pill: tuple[str, str] | None = None) -> str:
    p = f"<span class='gp-pill {esc(pill[1])}'>{esc(pill[0])}</span>" if pill else ""
    return (f"<div class='gp-card {esc(tone)}'><div class='l'>{esc(label)}</div><div class='v'>{esc(value)}</div>"
            f"<div class='s'>{esc(sub)} {p}</div></div>")


def grid(cards: list[str]) -> None:
    st.markdown("<div class='gp-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def load_json(path: str):
    p = ROOT / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def need(*paths: str) -> bool:
    """Friendly empty state. Returns True if everything is present."""
    missing = [p for p in paths if not (ROOT / p).exists()]
    if missing:
        st.info("No results yet. Run the pipeline first (see the README), then refresh. Missing: "
                + ", ".join(f"`{m}`" for m in missing))
        return False
    return True


def footer() -> None:
    st.markdown("<div class='gp-foot'>GrowPulse is an independent student project. Not affiliated with Groww. "
                "Data: public Play Store reviews, no usernames.</div>", unsafe_allow_html=True)
