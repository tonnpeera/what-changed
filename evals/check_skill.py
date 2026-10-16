#!/usr/bin/env python3
"""Check a skill folder against the Agent Skills specification (agentskills.io/specification).

Usage: python3 evals/check_skill.py skills/what-changed
Checks: name 1-64 chars, a-z0-9 and single hyphens, matches folder; description 1-1024 chars;
compatibility <= 500 chars if present; metadata values are strings; SKILL.md under 500 lines;
every relative link in SKILL.md points to an existing file.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def frontmatter(text: str) -> tuple[dict[str, str], dict[str, str]]:
    lines = text.splitlines()
    assert lines[0].strip() == "---", "SKILL.md must start with YAML frontmatter"
    top: dict[str, str] = {}
    meta: dict[str, str] = {}
    in_meta = False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("  ") and in_meta:
            k, v = line.strip().split(":", 1)
            meta[k.strip()] = v.strip()
            continue
        if ":" not in line:
            continue  # continuation of a multi-line value
        k, v = line.split(":", 1)
        top[k.strip()] = v.strip()
        in_meta = k.strip() == "metadata"
    return top, meta


def main(argv: list[str]) -> int:
    folder = Path(argv[1] if len(argv) > 1 else "skills/what-changed")
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    top, meta = frontmatter(text)
    name, desc = top.get("name", ""), top.get("description", "")
    checks = [
        ("name present and 1-64 chars", 1 <= len(name) <= 64),
        ("name is lowercase a-z0-9 with single hyphens", bool(NAME.match(name))),
        ("name matches folder name", name == folder.name),
        ("description 1-1024 chars", 1 <= len(desc) <= 1024),
        ("compatibility <= 500 chars if present", len(top.get("compatibility", "")) <= 500),
        ("metadata values are quoted strings", all(v.startswith('"') and v.endswith('"') for v in meta.values())),
        ("SKILL.md under 500 lines", len(text.splitlines()) < 500),
    ]
    links = re.findall(r"\]\(((?!https?://|#)[^)]+)\)", text)
    missing = [l for l in links if not (folder / l).exists()]
    checks.append((f"relative links resolve ({len(links)} links)", not missing))
    passed = sum(ok for _, ok in checks)
    print(f"check_skill {folder.name}: {passed}/{len(checks)} checks passed")
    for label, ok in checks:
        print(f"  {'pass' if ok else 'FAIL'}  {label}")
    for l in missing:
        print(f"  missing link target: {l}")
    print(f"  description: {len(desc)} chars · SKILL.md: {len(text.splitlines())} lines")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
