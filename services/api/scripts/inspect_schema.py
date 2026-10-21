"""Small schema introspection helper used during development.

Kept as a real module (rather than a throwaway script) because "what does the
migration actually produce?" is a question worth being able to re-ask. It is
not imported by the app or the test suite.

Usage::

    .\\.venv\\Scripts\\python.exe -m services.api.scripts.inspect_schema <sqlite-path>
"""

from __future__ import annotations

import sqlite3
import sys


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: inspect_schema <path-to-sqlite-db>")
        return 2
    conn = sqlite3.connect(args[0])
    names = sorted(
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    )
    print(f"{len(names)} tables:")
    for name in names:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')]
        print(f"  - {name}: {', '.join(cols)}")
    try:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        print("alembic version:", version)
    except sqlite3.OperationalError:
        print("alembic version: <no alembic_version table>")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
