"""Guardrails: the app only ever runs read-only SELECTs.

Every SQL string — from the LLM, from a saved dashboard, from anywhere —
passes through validate() before execution. No exceptions.
"""
import re

BLOCKED = {
    "drop", "delete", "insert", "update", "alter", "truncate",
    "grant", "revoke", "create", "merge", "vacuum", "optimize",
    "copy", "undrop",
}

DEFAULT_LIMIT = 200


def validate(sql_text: str) -> str:
    s = sql_text.strip().rstrip(";").strip()
    s = re.sub(r"--.*?$", "", s, flags=re.M).strip()          # line comments
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S).strip()       # block comments
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("Only SELECT queries are allowed.")
    tokens = set(re.findall(r"[a-z_]+", low))
    bad = sorted(BLOCKED & tokens)
    if bad:
        raise ValueError(f"Blocked keyword(s): {', '.join(bad)}")
    if not re.search(r"\blimit\b", low):
        s = f"{s} LIMIT {DEFAULT_LIMIT}"
    return s
