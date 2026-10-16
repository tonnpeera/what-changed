#!/usr/bin/env python3
"""Read the token count a host printed after a run and record it in runs.log.

Usage: python3 evals/host_tokens.py <host> <host-output-file> <store>

Agents cannot see their own usage while they run, so they write tokens=unknown.
The host prints it afterwards; this script reads it and, if the last runs.log
line still says tokens=unknown, fills it in. Prints what it found either way.

  codex        "tokens used" followed by a number (last occurrence)
  antigravity  JSON envelope: usage.total_tokens
  claude       JSON: usage.input_tokens + output_tokens + cache tokens
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _json(text: str) -> dict | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None


def tokens(host: str, text: str) -> int | None:
    if host.startswith("codex"):
        found = re.findall(r"tokens used\s*\n?\s*([\d,]+)", text)
        return int(found[-1].replace(",", "")) if found else None
    data = _json(text)
    if not data:
        return None
    if host == "antigravity":
        return (data.get("usage") or {}).get("total_tokens")
    if host == "claude":
        u = data.get("usage") or {}
        keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        return sum(u.get(k, 0) or 0 for k in keys) or None
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    host, out, store = argv[1], Path(argv[2]), Path(argv[3])
    if not out.exists():
        print("host_tokens: no host output file")
        return 0
    n = tokens(host, out.read_text(encoding="utf-8", errors="replace"))
    if n is None:
        print("host_tokens: the host did not report tokens in a form this script reads")
        return 0
    print(f"host_tokens: {n:,} tokens (host-reported)")
    log = store / "runs.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8").splitlines()
        if lines and "tokens=unknown" in lines[-1]:
            lines[-1] = lines[-1].replace("tokens=unknown", f"tokens={n}")
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print("host_tokens: filled in the last runs.log line")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
