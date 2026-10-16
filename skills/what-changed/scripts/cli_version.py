#!/usr/bin/env python3
"""Check an agent CLI's version before an unattended run, with a time limit.

Usage: python3 cli_version.py PATH MINIMUM [--timeout 30]

Runs `PATH --version` and compares the first x.y.z in its output with MINIMUM. A CLI that does
not answer within --timeout seconds (stuck in an update, waiting on the network) is stopped.
Used by run-daily.sh and run-daily.ps1, so both schedulers behave the same way.

Prints one line: the version, or why the check failed.
Exit codes: 0 version is at least MINIMUM · 3 older, unknown, or the CLI could not be started ·
4 no answer within the time limit. Standard library only.
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tempfile

if sys.version_info < (3, 11):  # keep in step with the README's "You need"
    sys.exit(f"what-changed needs Python 3.11 or later, not {sys.version.split()[0]}. Install a newer one from "
             "python.org or Homebrew (the python3 from Apple's command line tools can be 3.9).")

VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def check(path: str, minimum: str, timeout: float) -> tuple[int, str]:
    # Output goes to a file, not a pipe: a child process the CLI started could keep a pipe open
    # after the CLI itself is stopped, and reading it would hang.
    with tempfile.TemporaryFile() as out:
        try:
            subprocess.run([path, "--version"], stdout=out, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return 4, f"{path} --version did not answer within {timeout:g} seconds"
        except OSError as e:
            return 3, f"{path} could not be started: {e.strerror or e}"
        out.seek(0)
        text = out.read(4096).decode("utf-8", errors="replace")
    m, floor = VERSION.search(text), VERSION.search(minimum)
    if not floor:
        return 3, f"minimum must look like x.y.z, not {minimum!r}"
    if not m:
        return 3, f"{path} is of unknown version (it printed {text.strip()[:80]!r})"
    have, need = tuple(map(int, m.groups())), tuple(map(int, floor.groups()))
    if have < need:
        return 3, f"{path} is version {m.group(0)}; {minimum} or later is needed"
    return 0, m.group(0)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("minimum")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args(argv[1:])
    code, line = check(args.path, args.minimum, args.timeout)
    print(line)
    return code


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to a legacy code page
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
