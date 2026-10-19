"""Phase 7: human-approved publishing through MCP (n8n). Nothing is written unless you type APPROVE.

Flow
  build exact doc entry + email  ->  print both in full  ->  SHA-256 fingerprint  ->  type APPROVE
  after APPROVE, in this order:
    1 read_doc (stop if this week's entry already exists; resume if only the draft is missing)
    2 re-check hash   3 append_to_doc   4 read_doc again (entry must be there)
    5 re-check hash   6 create_email_draft          (there is no send tool)
Every step is logged to logs/. Anything other than APPROVE = reject: ask why, write nothing.

Usage:  python approve.py            interactive
        python approve.py --dry-run  build + print + hash only (no prompt, no MCP calls)
"""
import asyncio
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

from src.mcp_tools import McpConfigError, open_session, text_of

OUT = Path("outputs")
LOGS = Path("logs")
SEP = "\n\x00\n"


def norm(t: str) -> str:
    return " ".join(t.split())


def build() -> dict:
    """Assemble the exact text that will be published, from the generated output files."""
    pulse_meta = json.loads((OUT / "pulse_parts.json").read_text(encoding="utf-8"))
    fee = json.loads((OUT / "fee_issue.json").read_text(encoding="utf-8"))
    exp = json.loads((OUT / "fee_explainer.json").read_text(encoding="utf-8"))
    pulse = (OUT / "weekly_pulse.md").read_text(encoding="utf-8").strip()
    today = date.today().isoformat()
    week = pulse_meta["week_label"].split()[2]                      # "week of YYYY-MM-DD ..."
    entry_id = f"review-pulse-{week}"

    issue = fee["fee_issue"]
    fee_line = (f"{issue.replace('_', ' ').title()}: {fee['confused_by_fee'][issue]} of "
                f"{fee['stance_counts']['confused']} confused fee reviews "
                f"({fee['keyword_candidates']} fee-related reviews checked)")
    bullets = [f"- {b['text']}" for b in exp["bullets"]]
    links = [f"- {l['title']}: {l['url']}" for l in exp["source_links"]]
    snippet = "\n".join(bullets + ["", "Sources:"] + links + [f"Last checked: {exp['last_checked']}"])

    doc_entry = "\n".join([
        f"=== WEEKLY PULSE ENTRY | ENTRY_ID: {entry_id} ===",
        f"date: {today}",
        f"top_themes: {'; '.join(pulse_meta['top_themes'])}",
        "weekly_pulse:", pulse,
        f"identified_fee_issue: {fee_line}",
        "explanation_bullets:", *bullets,
        "source_links:", *links,
        f"last_checked: {exp['last_checked']}",
        f"=== END {entry_id} ===", ""])
    subject = f"Weekly Product Pulse + Customer Clarification — {today}"
    body = "\n".join([pulse, "", "---", "Reusable support snippet (fee explainer)", "", snippet, ""])

    OUT.mkdir(exist_ok=True)
    (OUT / "email_draft.txt").write_text(f"Subject: {subject}\n\n{body}", encoding="utf-8")
    src_meta = json.loads(Path("data/sources.json").read_text(encoding="utf-8"))
    used = {l["url"] for l in exp["source_links"]}
    (OUT / "sources.md").write_text("# Sources (fetched " + exp["last_checked"] + ")\n\n" + "\n".join(
        f"- {s['title']}: {s['url']}" + (" (cited in fee explainer)" if s["url"] in used else " (cross-check only)")
        for s in src_meta) + "\n", encoding="utf-8")
    return {"entry_id": entry_id, "doc_entry": doc_entry, "subject": subject, "body": body,
            "needs_review": bool(exp.get("needs_human_review")) or pulse_meta.get("status") != "OK",
            "hash": hashlib.sha256((doc_entry + SEP + subject + SEP + body).encode("utf-8")).hexdigest()}


class Log:
    def __init__(self):
        LOGS.mkdir(exist_ok=True)
        self.path = LOGS / f"approve_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    def __call__(self, step: str, status: str, **detail):
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "step": step, "status": status, **detail}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  [{status}] {step}")


def state_path(entry_id: str) -> Path:
    return LOGS / f"state_{entry_id}.json"


def load_state(entry_id: str) -> dict:
    p = state_path(entry_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(entry_id: str, **kw) -> None:
    LOGS.mkdir(exist_ok=True)
    st = {**load_state(entry_id), **kw}
    state_path(entry_id).write_text(json.dumps(st), encoding="utf-8")


def text_param(tool, prefer: str) -> str:
    """Name of the single required string parameter of a tool (read from its MCP schema)."""
    req = tool.input_schema.get("required", [])
    if prefer in req:
        return prefer
    return req[0] if len(req) == 1 else prefer


async def publish(approved: dict, log: Log) -> bool:
    def still_same(label: str) -> None:
        fresh = build()
        if fresh["hash"] != approved["hash"]:
            log(label, "FAIL", approved=approved["hash"], now=fresh["hash"])
            raise RuntimeError("The text changed after you approved it, so nothing more was written.")
        log(label, "ok", sha256=fresh["hash"])

    eid, state = approved["entry_id"], load_state(approved["entry_id"])
    async with open_session() as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        if set(tools) != {"append_to_doc", "read_doc", "create_email_draft"} or any("send" in n for n in tools):
            raise RuntimeError("The MCP server does not expose exactly the 3 expected tools.")
        pname = text_param(tools["append_to_doc"], "Text")
        if "old_text" in pname.lower():
            raise RuntimeError("append_to_doc in n8n is set to 'Replace Text', not 'Insert'; fix the node "
                               "(Actions > Insert, Text set by the model) and try again. Nothing was written.")

        r = await s.call_tool("read_doc", {})
        before = text_of(r)
        log("1 read_doc (duplicate check)", "ok", chars=len(before))
        landed = norm(approved["doc_entry"]) in norm(before)
        if f"ENTRY_ID: {eid}" in before and not landed:
            raise RuntimeError("An entry for this week exists in the doc but differs from this text; stopping.")
        if landed and state.get("draft_created"):
            log("1 read_doc", "STOP", reason="already published and drafted")
            print("This week is already published and the draft exists. Nothing to do.")
            return True

        if not landed:
            still_same("2 re-check hash")
            r = await s.call_tool("append_to_doc", {pname: approved["doc_entry"]})
            if r.is_error:
                raise RuntimeError("append_to_doc returned an error.")
            log("3 append_to_doc", "ok")
            save_state(eid, doc_appended=True, hash=approved["hash"])
            after = text_of(await s.call_tool("read_doc", {}))
            if norm(approved["doc_entry"]) not in norm(after):
                log("4 read_doc (verify)", "FAIL")
                raise RuntimeError("The doc was written but the entry could not be read back; check the doc.")
            log("4 read_doc (verify)", "ok", chars=len(after))
        else:
            log("3 append_to_doc", "skipped", reason="entry already in doc (resume)")

        still_same("5 re-check hash")
        r = await s.call_tool("create_email_draft", {"Subject": approved["subject"], "Message": approved["body"]})
        if r.is_error:
            raise RuntimeError("create_email_draft returned an error.")
        log("6 create_email_draft", "ok", result=text_of(r)[:200])
        save_state(eid, draft_created=True)
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    approved = build()
    print("=" * 70, "\nGOOGLE DOC ENTRY (exact text):\n", "=" * 70, sep="")
    print(approved["doc_entry"])
    print("=" * 70, f"\nGMAIL DRAFT\nSubject: {approved['subject']}\n", "=" * 70, sep="")
    print(approved["body"])
    print("=" * 70, f"\nSHA-256: {approved['hash']}\n", "=" * 70, sep="")
    if approved["needs_review"]:
        print("BLOCKED: the pulse or fee explainer is marked NEEDS HUMAN REVIEW / failed limits.")
        return 2
    if "--dry-run" in sys.argv:
        print("dry run: nothing sent, no prompt.")
        return 0

    log = Log()
    answer = input("Type APPROVE (exact, capitals) to write the doc entry and create the Gmail draft: ")
    if answer != "APPROVE":
        reason = input("Rejected. Why? ")
        log("approval", "REJECTED", reason=reason, sha256=approved["hash"])
        print("Nothing was written.")
        return 1
    log("approval", "APPROVED", sha256=approved["hash"])
    try:
        asyncio.run(publish(approved, log))
    except McpConfigError as e:
        log("error", "FAIL", detail=repr(e))
        print(f"Could not finish: {e}")
        return 1
    except Exception as e:                       # noqa: BLE001 - friendly sentence, detail in the log
        log("error", "FAIL", detail=repr(e))
        print(f"Stopped: {e} (details in {log.path})")
        return 1
    print(f"\nDone. Check your Google Doc and Gmail Drafts. Log: {log.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
