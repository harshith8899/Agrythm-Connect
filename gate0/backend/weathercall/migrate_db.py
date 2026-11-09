"""Copies the data in a SQLite file into Postgres (Supabase).

  python -m weathercall.migrate_db --from weathercall.db --to "postgresql://..." [--dry-run]

Safe to repeat: rows already in Postgres are left alone (INSERT OR IGNORE). Only counts are printed, never farmer data.
The tables are created in the Postgres schema (GATE0_DB_SCHEMA, default "agrythm") if they are not there yet.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

from .adapters.dialers import MockDialler
from .db import connect, is_postgres, table_columns
from .service import DashboardService

TABLES = ("dash_farmers", "dash_results", "dash_callbacks", "dash_retries", "dash_settings", "dash_stops", "dash_declines",
          "dash_paused", "dash_alerts", "dash_tests", "attempts", "day_results", "weather")
SERIAL = {"dash_alerts": "id", "dash_tests": "id"}      # tables whose id counts up by itself


def migrate(source: str, target: str, dry_run: bool = False) -> dict[str, tuple[int, int]]:
    """Returns {table: (rows in SQLite, rows added to Postgres)}."""
    if not is_postgres(target):
        raise ValueError("--to must be a postgres:// address")
    src = sqlite3.connect(source)
    have = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    result: dict[str, tuple[int, int]] = {}
    dst = None
    if not dry_run:
        service = DashboardService(target, dialler=MockDialler(), env={"GATE0_WEATHER": "mock"})
        service._make_ports()                       # also creates attempts, day_results and weather
        dst = connect(target)
    for table in TABLES:
        if table not in have:
            continue
        cols = sorted(table_columns(src, table), key=lambda c: [r[1] for r in src.execute(f"PRAGMA table_info({table})")].index(c))
        rows = src.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
        types = {r[1]: (r[2] or "").upper() for r in src.execute(f"PRAGMA table_info({table})")}
        numeric = [i for i, c in enumerate(cols) if types.get(c, "").startswith(("INT", "REAL"))]
        # SQLite let an empty string sit in a number column; Postgres does not: that is NULL
        rows = [tuple(None if (i in numeric and v == "") else v for i, v in enumerate(r)) for r in rows]
        added = 0
        if not dry_run:
            sql = f"INSERT OR IGNORE INTO {table}({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})"
            for row in rows:
                added += dst.execute(sql, row).rowcount or 0
            if table in SERIAL:
                col = SERIAL[table]
                dst.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                            f"COALESCE((SELECT MAX({col}) FROM {table}), 1))")
        result[table] = (len(rows), added)
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--from", dest="source", required=True, help="the SQLite file")
    p.add_argument("--to", dest="target", required=True, help="the postgres:// address")
    p.add_argument("--dry-run", action="store_true", help="only count the rows")
    a = p.parse_args(argv)
    for table, (found, added) in migrate(a.source, a.target, a.dry_run).items():
        print(f"{table:<14} {found:>6} rows" + ("" if a.dry_run else f", {added} added"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
