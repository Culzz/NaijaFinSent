"""Run each test file in a subprocess with a hard timeout, report the verdict.

Used during the build to locate hanging tests without the whole suite stalling.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIMEOUT = 300


def main() -> int:
    files = sorted(p.name for p in (ROOT / "tests").glob("test_*.py"))
    only = sys.argv[1:] or files
    for name in only:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", f"tests/{name}", "-q",
                 "-p", "no:cacheprovider", "--no-header"],
                cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
                encoding="utf-8", errors="replace",
            )
            tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
            verdict = tail[-1] if tail else "(no output)"
            status = "PASS" if proc.returncode == 0 else "FAIL"
            print(f"{status}  {name}  :: {verdict[:120]}")
        except subprocess.TimeoutExpired:
            print(f"HANG  {name}  :: exceeded {TIMEOUT}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
