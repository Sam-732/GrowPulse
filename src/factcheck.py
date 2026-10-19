"""Small deterministic fact checks reused by the app (same rules as explainer.py's code check)."""
import re
from pathlib import Path

CUT_MARKERS = ["Was the answer helpful?", "Vaishnavi Tech Park"]
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def source_text(source_id: str, root: Path = Path(".")) -> str:
    t = (root / "data" / "sources" / f"{source_id}.txt").read_text(encoding="utf-8")
    for m in CUT_MARKERS:
        i = t.find(m)
        t = t[:i] if i > 0 else t
    return t


def squash(t: str) -> str:
    return re.sub(r"[\s|]+", "", t)


def numbers(t: str) -> set[str]:
    return {n.rstrip(".,").replace(",", "") for n in _NUM.findall(t)}


def numbers_in_source(bullet: str, source_id: str) -> bool:
    return numbers(bullet) <= numbers(source_text(source_id))


def evidence_verbatim(evidence, source_id: str) -> bool:
    snippets = [str(x) for x in (evidence if isinstance(evidence, list) else [evidence]) if str(x).strip()]
    sq = squash(source_text(source_id))
    return bool(snippets) and all(squash(x) in sq for x in snippets)
