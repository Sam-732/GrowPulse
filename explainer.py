"""Phase 5b: RAG-grounded fee explainer (<=6 bullets) + code number check + LLM judge.

Pipeline: trimmed official pages -> chunks -> MiniLM embeddings (same ONNX MiniLM-L6-v2 that
GrowChat uses, via chromadb) -> Chroma retrieval -> LLM writes bullets from retrieved chunks only
-> (1) code: every number must appear in the cited source, no opinion words, valid source id
-> (2) judge LLM: is every claim directly stated in the cited source? -> rejected bullets are
regenerated once, then dropped. Fewer than 3 survivors => NEEDS HUMAN REVIEW.
Source links are hardcoded in fetch_sources.py; the LLM never writes a URL.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from dotenv import load_dotenv

from src.llm import chat_json

load_dotenv()

SRC_DIR, SRC_JSON = Path("data/sources"), Path("data/sources.json")
CHROMA_DIR = Path("chroma")
OUT_MD, OUT_JSON = Path("outputs/fee_explainer.md"), Path("outputs/fee_explainer.json")
FEE_ISSUE = json.loads(Path("outputs/fee_issue.json").read_text(encoding="utf-8"))["fee_issue"]

EXPLAINER_SOURCES = ["pricing", "help_delivery"]      # the 2 official links shown to customers
MAX_BULLETS, MIN_SURVIVORS, MAX_TRIES = 6, 3, 3
JUDGE_MODEL = os.getenv("GROQ_JUDGE_MODEL", "openai/gpt-oss-120b")
CHUNK_CHARS, TOP_K = 600, 4
CUT_MARKERS = ["Was the answer helpful?", "Vaishnavi Tech Park"]    # page footer boilerplate
OPINION = re.compile(r"\b(cheap|expensive|unfair|overpriced|reasonable|best|worst|hidden|scam|"
                     r"high|low|affordable|costly|steep)\b", re.I)
NUM = re.compile(r"\d+(?:[.,]\d+)*")
QUERIES = [
    "What is brokerage on Groww and how is it calculated",
    "brokerage for delivery and intraday equity orders lower of rupees or percent of trade value",
    "DP charges when selling shares from demat account",
    "charges set by exchanges, SEBI and government: transaction charges, stamp duty, STT",
    "GST applied on brokerage and other charges",
    "why total brokerage can be more than 20 rupees multiple orders",
]


def trim(text: str) -> str:
    for m in CUT_MARKERS:
        i = text.find(m)
        if i > 0:
            text = text[:i]
    return text.strip()


def chunk(text: str) -> list[str]:
    out, cur = [], ""
    for line in text.splitlines():
        if cur and len(cur) + len(line) > CHUNK_CHARS:
            out.append(cur.strip())
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur.strip())
    return out


def squash(t: str) -> str:
    """Whitespace/table-pipe-insensitive form used only for the verbatim-evidence test."""
    return re.sub(r"[\s|]+", "", t)


def nums(text: str) -> set[str]:
    return {n.rstrip(".,").replace(",", "") for n in NUM.findall(text)}


def build_index(sources: dict[str, dict]):
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False))
    col = client.create_collection("groww_fee_pages", embedding_function=None, metadata={"hnsw:space": "cosine"})
    emb = ONNXMiniLM_L6_V2()
    ids, docs, metas = [], [], []
    for sid, s in sources.items():
        for i, c in enumerate(chunk(s["text"])):
            ids.append(f"{sid}-{i}")
            docs.append(c)
            metas.append({"source": sid, "url": s["url"]})
    col.add(ids=ids, documents=docs, metadatas=metas, embeddings=[list(map(float, v)) for v in emb(docs)])
    return col, emb, len(ids)


def retrieve(col, emb, allowed: list[str]) -> list[dict]:
    seen, hits = set(), []
    for q in QUERIES:
        res = col.query(query_embeddings=[list(map(float, emb([q])[0]))], n_results=TOP_K,
                        where={"source": {"$in": allowed}})
        for cid, doc, meta in zip(res["ids"][0], res["documents"][0], res["metadatas"][0]):
            if cid not in seen:
                seen.add(cid)
                hits.append({"id": cid, "source": meta["source"], "text": doc})
    return hits


def context_block(hits) -> str:
    return "\n\n".join(f"[source: {h['source']}]\n{h['text']}" for h in hits)


def generate(hits, attempt: int, extra: str = "") -> list[dict]:
    out = chat_json([
        {"role": "system", "content": (
            "You write a neutral, facts-only fee explainer for support agents. Use ONLY the CONTEXT chunks. "
            "No opinions, no advice, no comparisons, no words like cheap/expensive/high/low. Do not write URLs. "
            "Copy numbers exactly as they appear in the context.")},
        {"role": "user", "content": (
            f"Topic: {FEE_ISSUE} charges on Groww (customers are confused about what they are charged and why).\n"
            f"Write AT MOST {MAX_BULLETS} bullets in this order: (1) what brokerage is, (2) the equity brokerage "
            "amount, (3) the DP charge on selling shares, (4) the charges set by exchanges/SEBI/government rather "
            "than Groww (NO numbers in this bullet; say who charges what), (5) GST on top, (6) account opening or "
            "maintenance charges. Skip any bullet the context does not state. Each bullet is ONE sentence, max 30 "
            "words, makes no claim beyond its evidence (never add qualifiers like 'intraday', 'all', 'per trade' "
            "unless the evidence says so), and cites exactly one source id. 'evidence' is ONE contiguous sentence or "
            "line copied character-for-character from that source's context (join table cells with single spaces).\n"
            'Return JSON: {"bullets":[{"text":"...","source":"pricing","evidence":["...","..."]}]}\n\n'
            "CONTEXT:\n" + context_block(hits) + extra)}], nocache_salt=f"gen{attempt}")
    return [b for b in out.get("bullets", []) if isinstance(b, dict)]


def code_check(b: dict, sources) -> list[str]:
    errs, text, sid = [], str(b.get("text", "")), b.get("source")
    if sid not in EXPLAINER_SOURCES or sid not in sources:
        return [f"source '{sid}' is not an allowed source"]
    src_nums = nums(sources[sid]["text"])
    missing = sorted(n for n in nums(text) if n not in src_nums)
    if missing:
        errs.append(f"numbers not in cited source: {missing}")
    raw = b.get("evidence", "")
    snippets = [str(x) for x in (raw if isinstance(raw, list) else [raw]) if str(x).strip()][:3]
    src_sq = squash(sources[sid]["text"])
    if not snippets or any(squash(x) not in src_sq for x in snippets):
        errs.append("evidence is not a verbatim excerpt of the cited source")
    elif not nums(text) <= nums(" ".join(snippets)):
        errs.append("bullet has numbers that are not in its evidence")
    if OPINION.search(text):
        errs.append("opinion word")
    if re.search(r"https?://|www\.", text):
        errs.append("URL in text")
    return errs


def judge(b: dict, sources) -> tuple[bool, str]:
    out = chat_json([
        {"role": "system", "content": "You are a strict fact-checker."},
        {"role": "user", "content": (
            f"SOURCE TEXT:\n{sources[b['source']]['text']}\n\nBULLET:\n{b['text']}\n\n"
            "Is EVERY claim in the bullet directly stated in the source text? A claim whose numbers are attached "
            "to the wrong thing, or that merges two different rules, is NOT directly stated. "
            'Return JSON {"every_claim_stated":true|false,"unsupported":"<the claim that is not stated, or empty>"}')}], model=JUDGE_MODEL)
    return bool(out.get("every_claim_stated")) is True, str(out.get("unsupported", ""))


def repair(b: dict, why: str, hits, tag: str) -> dict | None:
    got = generate(hits, 10, extra=(
        f"\n\nREWRITE ONLY this bullet so it is fully supported by the context. Problem: {why}\n"
        f"Bullet: {b['text']}\nReturn JSON with exactly ONE bullet in the same format."))
    return got[0] if got else None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    meta = {m["id"]: m for m in json.loads(SRC_JSON.read_text(encoding="utf-8"))}
    sources = {sid: {**m, "text": trim((SRC_DIR / f"{sid}.txt").read_text(encoding="utf-8"))}
               for sid, m in meta.items()}
    col, emb, n_chunks = build_index({k: v for k, v in sources.items() if k in EXPLAINER_SOURCES})
    hits = retrieve(col, emb, EXPLAINER_SOURCES)
    print(f"indexed {n_chunks} chunks from {EXPLAINER_SOURCES}; retrieved {len(hits)} unique chunks")

    bullets = []
    for attempt in range(MAX_TRIES):
        bullets = generate(hits, attempt)
        print(f"attempt {attempt + 1}: {len(bullets)} bullets")
        if len(bullets) <= MAX_BULLETS:
            break
    bullets = bullets[:MAX_BULLETS]                      # hard cap in code

    report, survivors, audit = [], [], []
    for b in bullets:
        status, cur = [], b
        for round_ in range(2):                          # original + one regeneration
            errs = code_check(cur, sources)
            verdict, why = (False, "; ".join(errs)) if errs else judge(cur, sources)
            status.append(("code" if errs else "judge", "REJECT" if not verdict else "PASS", why))
            if verdict:
                survivors.append(cur)
                break
            if round_ == 0:
                nxt = repair(cur, why, hits, "r")
                if not nxt:
                    break
                cur = nxt
        passed = any(res == "PASS" for _, res, _ in status)
        report.append((b["text"], status))
        audit.append({"draft": b["text"], "final": survivors[-1]["text"] if passed else None,
                      "source": (survivors[-1]["source"] if passed else b.get("source")),
                      "regenerated": len(status) > 1, "dropped": not passed,
                      "checks": [{"stage": st, "result": res, "reason": why} for st, res, why in status]})

    print("\nBULLET CHECKS:")
    for text, st in report:
        print(f"- {text}")
        for stage, res, why in st:
            print(f"    {stage:5} {res}  {why}")

    needs_review = len(survivors) < MIN_SURVIVORS
    checked = max(meta[s]["fetched"] for s in EXPLAINER_SOURCES)
    lines = [f"# Fee explainer: {FEE_ISSUE.replace('_', ' ').title()} on Groww"]
    if needs_review:
        lines += ["", "**NEEDS HUMAN REVIEW** (fewer than 3 bullets passed the checks)"]
    lines += [""] + [f"- {b['text']} [{b['source']}]" for b in survivors]
    lines += ["", "Sources:"] + [f"- {meta[s]['title']}: {meta[s]['url']}" for s in EXPLAINER_SOURCES]
    lines += ["", f"Last checked: {checked}", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps({
        "fee_issue": FEE_ISSUE, "bullets": survivors, "needs_human_review": needs_review,
        "dropped": len(bullets) - len(survivors), "last_checked": checked,
        "judge_model": JUDGE_MODEL, "audit": audit,
        "source_links": [{"title": meta[s]["title"], "url": meta[s]["url"]} for s in EXPLAINER_SOURCES],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsurvivors: {len(survivors)}/{len(bullets)} | NEEDS HUMAN REVIEW: {needs_review}\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
