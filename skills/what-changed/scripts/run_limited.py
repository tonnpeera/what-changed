#!/usr/bin/env python3
"""Run one of the skill's scripts with a time limit (macOS has no `timeout` command).

Usage: python3 run_limited.py SECONDS SCRIPT [ARG ...]
Runs SCRIPT with this same Python in isolated mode (-I) and exits with its exit code. If it is
still running after SECONDS, it is stopped, a line goes to stderr and the exit code is 124 (as
GNU timeout uses). The schedulers use it as a backstop: the scripts have their own time budgets,
and this also covers anything those miss. Standard library only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TIMED_OUT = 124


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) == 2 else 2
    seconds = float(argv[1])
    try:
        return subprocess.run([sys.executable, "-I", *argv[2:]], timeout=seconds).returncode
    except subprocess.TimeoutExpired:  # run() has already stopped the script
        print(f"run_limited: {Path(argv[2]).name} did not finish within {seconds:g} s and was stopped", file=sys.stderr)
        return TIMED_OUT


if __name__ == "__main__":
    sys.exit(main(sys.argv))
