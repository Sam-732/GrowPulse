"""Fee/charge keyword filter, shared by Phase 1 (counts) and Phase 3 (fee detection)."""
import re

# label -> regex. Case-insensitive; word boundaries stop "dp" matching inside words.
KEYWORDS = {
    "charge":     r"\bcharg(?:e|es|ed|ing)\b",
    "fee":        r"\bfees?\b",
    "exit load":  r"\bexit[\s-]*loads?\b",
    "deducted":   r"\bdeduct(?:ed|ion|ions|s)?\b",
    "brokerage":  r"\bbrokerage\b",
    "DP":         r"\bdp\b",
    "AMC":        r"\bamc\b",
    "hidden":     r"\bhidden\b",
    "GST":        r"\bgst\b",
    "commission": r"\bcommission\b",
    "extra":      r"\bextra\b",
    "cut":        r"\bcut(?:s|ting)?\b",
    "₹":          r"₹",
}
_COMPILED = {k: re.compile(v, re.I) for k, v in KEYWORDS.items()}


def matched_keywords(text: str) -> list[str]:
    return [k for k, rx in _COMPILED.items() if rx.search(text or "")]
