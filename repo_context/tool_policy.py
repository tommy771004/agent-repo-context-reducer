from __future__ import annotations

import re
from typing import Any

DESTRUCTIVE = [r"\brm\s+-rf\b", r"\bgit\s+reset\s+--hard\b", r"\bgit\s+clean\s+-[a-z]*f", r"\bdrop\s+(table|database)\b", r"\btruncate\s+table\b"]
WRITE = [r"\bgit\s+(commit|push|merge|rebase)\b", r"\bnpm\s+publish\b", r"\bterraform\s+apply\b", r"\bkubectl\s+(apply|delete|patch)\b"]
CREDENTIAL = [r"\b(cat|type|read)\b.*(?:\.env|id_rsa|credentials|secret|token)", r"\bprintenv\b", r"\benv\b"]
EXTERNAL = [r"\bcurl\b", r"\bwget\b", r"\bssh\b", r"\bscp\b", r"\bgh\s+api\b"]


def classify_command(command: str) -> dict[str, Any]:
    lower = command.lower()
    def hit(patterns: list[str]) -> bool:
        return any(re.search(p, lower, re.I) for p in patterns)
    if hit(DESTRUCTIVE):
        risk, permission = "destructive", "confirmation-required"
    elif hit(CREDENTIAL):
        risk, permission = "credential-access", "confirmation-or-explicit-policy"
    elif hit(WRITE):
        risk, permission = "write", "explicit-write-policy"
    elif hit(EXTERNAL):
        risk, permission = "external-side-effect", "network-policy"
    else:
        risk, permission = "read-only-or-unknown", "normal"
    return {
        "command": command, "risk": risk, "permission": permission,
        "classification": "deterministic-pattern-policy",
        "note": "Unknown commands are not proven safe; this classifier is a guard, not a sandbox.",
    }
