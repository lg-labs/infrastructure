"""Server-side env-var redaction (design.md §8.4)."""
from __future__ import annotations

import re
from typing import Iterable

# Match common secret-bearing key suffixes. Case-insensitive.
SECRET_RE = re.compile(r"(?i)(password|secret|token|key|credential)")

REDACTED = "<redacted>"


def is_secret_key(key: str) -> bool:
    return bool(SECRET_RE.search(key or ""))


def redact_env_pair(key: str, value: str) -> tuple[str, str]:
    if is_secret_key(key):
        return key, REDACTED
    return key, value


def redact_env_list(env: Iterable[str]) -> list[dict[str, str]]:
    """Take docker-py raw env list ('K=V' strings) and return [{key, value}]."""
    out: list[dict[str, str]] = []
    for line in env or []:
        if "=" not in line:
            out.append({"key": line, "value": ""})
            continue
        k, v = line.split("=", 1)
        rk, rv = redact_env_pair(k, v)
        out.append({"key": rk, "value": rv})
    return out


def redact_env_dict(env: dict[str, str]) -> dict[str, str]:
    """Same logic for env dicts (used when input is already a mapping)."""
    return {k: (REDACTED if is_secret_key(k) else v) for k, v in (env or {}).items()}
