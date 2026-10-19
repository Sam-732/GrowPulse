"""Reads the approve logs (logs/approve_*.jsonl) into run summaries for the app. Read-only."""
import json
from pathlib import Path

LOGS = Path("logs")


def _read(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _step_ok(recs: list[dict], prefix: str, statuses=("ok",)) -> bool:
    return any(r["step"].startswith(prefix) and r["status"] in statuses for r in recs)


def runs() -> list[dict]:
    """Newest first. Each run: started, outcome, steps (list of records), flags."""
    result = []
    for p in sorted(LOGS.glob("approve_*.jsonl"), reverse=True):
        recs = _read(p)
        if not recs:
            continue
        approval = next((r for r in recs if r["step"] == "approval"), {})
        err = next((r for r in recs if r["step"] == "error"), None)
        doc = _step_ok(recs, "3 append_to_doc", ("ok", "skipped"))
        verified = _step_ok(recs, "4 read_doc")
        draft = _step_ok(recs, "6 create_email_draft")
        status = approval.get("status", "")
        if status == "REJECTED":
            outcome = "Rejected, nothing written"
        elif draft:
            outcome = "Published: entry in Doc + Gmail draft"
        elif doc and err:
            outcome = "Partial: entry in Doc, draft not created"
        elif err:
            outcome = "Failed before writing"
        else:
            outcome = "Approved, not completed"
        result.append({"file": p.name, "started": recs[0]["ts"], "outcome": outcome, "approval": status,
                       "reason": approval.get("reason", ""), "sha256": approval.get("sha256", ""),
                       "doc_appended": doc, "verified": verified, "draft": draft,
                       "error": (err or {}).get("detail", ""), "steps": recs})
    return result


def overall() -> dict:
    """Combined state across runs (a resume run can finish what an earlier run started)."""
    rs = runs()
    doc = any(r["doc_appended"] for r in rs)
    draft = any(r["draft"] for r in rs)
    last = rs[0] if rs else None
    if draft:
        label, tone = "Published", "ok"
    elif doc:
        label, tone = "Entry in Doc, draft pending", "warn"
    elif last and last["approval"] == "REJECTED":
        label, tone = "Last run rejected", "muted"
    else:
        label, tone = "Not published yet", "muted"
    return {"label": label, "tone": tone, "doc": doc, "draft": draft, "last": last, "runs": len(rs)}
