"""One way to open the database.

Default: a SQLite file (local work and the test suite). When the target is a postgres:// URL (Supabase), the same SQL
runs on Postgres through PgConnection, which has the small part of the sqlite3 interface this code uses: execute,
executemany, executescript, commit, rollback, close, and cursors with fetchone, fetchall and rowcount.

Postgres notes
- The tables live in their own schema (GATE0_DB_SCHEMA, default "agrythm"), not in "public", because Supabase exposes
  "public" through its REST API. Row level security is also switched on for every table, so the public API keys see nothing.
- Autocommit is on: each statement is its own transaction, so one failed statement cannot poison the shared connection.
- The SQL written for SQLite is translated: ? placeholders, INSERT OR REPLACE and INSERT OR IGNORE, AUTOINCREMENT, REAL.
- GATE0_TEST_DATABASE_URL runs the test suite on Postgres: every SQLite path (or :memory:) is then mapped to its own
  throwaway schema, dropped at the end of the run (see tests/conftest.py).
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:                                    # only needed when a postgres:// URL is used
    import psycopg
except ImportError:                     # pragma: no cover
    psycopg = None

DEFAULT_SCHEMA = "agrythm"

IntegrityError: tuple = (sqlite3.IntegrityError,) + ((psycopg.errors.IntegrityError,) if psycopg else ())
OperationalError: tuple = (sqlite3.OperationalError,) + (
    (psycopg.OperationalError, psycopg.errors.UndefinedTable) if psycopg else ())

_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ready: set[tuple] = set()              # (url, schema, script hash) already created in this process
test_schemas: list[tuple[str, str]] = []  # (url, schema) created for a test run


def is_postgres(target) -> bool:
    return str(target).startswith(("postgres://", "postgresql://"))


# ---- SQL translation (pure, so it can be tested without a database) --------------------------------------------------
def qmarks(sql: str) -> str:
    """? placeholders become %s (outside quotes) and a literal % is doubled, as the Postgres driver wants."""
    out, quote = [], False
    for ch in sql:
        if ch == "'":
            quote = not quote
        if ch == "%":
            out.append("%%")
        elif ch == "?" and not quote:
            out.append("%s")
        else:
            out.append(ch)
    return "".join(out)


_OR_REPLACE = re.compile(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*(?:\(([^)]*)\))?\s*VALUES\s*(\(.*\))\s*$", re.I | re.S)
_OR_IGNORE = re.compile(r"^(\s*INSERT)\s+OR\s+IGNORE(\s+INTO\s+.*)$", re.I | re.S)


def translate(sql: str, table_info=None) -> str:
    """SQLite SQL -> Postgres SQL. table_info(name) -> (columns, primary key columns), needed for INSERT OR REPLACE."""
    m = _OR_REPLACE.match(sql)
    if m:
        table, cols_txt, values = m.group(1), m.group(2), m.group(3)
        all_cols, pk = table_info(table)
        n = values.count("?")
        cols = [c.strip() for c in cols_txt.split(",")] if cols_txt else all_cols[:n]
        sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in pk)
        action = f"DO UPDATE SET {sets}" if sets else "DO NOTHING"
        return qmarks(f"INSERT INTO {table}({', '.join(cols)}) VALUES {values} ON CONFLICT ({', '.join(pk)}) {action}")
    m = _OR_IGNORE.match(sql)
    if m:
        return qmarks(f"{m.group(1)}{m.group(2)} ON CONFLICT DO NOTHING")
    return qmarks(sql)


def translate_ddl(sql: str) -> str:
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql, flags=re.I)
    sql = re.sub(r'\bTEXT\b(?!\s+COLLATE)', 'TEXT COLLATE "C"', sql, flags=re.I)   # byte order: ISO timestamps compare as text
    return sql


# ---- Postgres connection with the sqlite3-like surface -------------------------------------------------------------------
class PgConnection:
    def __init__(self, url: str, schema: str | None = None):
        if psycopg is None:
            raise RuntimeError("Postgres needs the psycopg package: pip install \"psycopg[binary]\"")
        parts = urlparse(url)
        query = dict(parse_qsl(parts.query))
        self.schema = schema or query.pop("schema", None) or os.environ.get("GATE0_DB_SCHEMA") or DEFAULT_SCHEMA
        if not _SCHEMA_NAME.match(self.schema):
            raise ValueError("the database schema name may only hold letters, digits and underscores")
        self.url = urlunparse(parts._replace(query=urlencode(query)))
        self._info: dict[str, tuple[list[str], list[str]]] = {}
        self._lock = threading.RLock()
        self._conn = None
        self._connect()

    def _connect(self) -> None:
        self._conn = psycopg.connect(self.url, autocommit=True, prepare_threshold=None, connect_timeout=15)
        self._conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
        self._conn.execute(f'SET search_path TO "{self.schema}"')

    def _table_info(self, table: str) -> tuple[list[str], list[str]]:
        if table not in self._info:
            cols = [r[0] for r in self._run(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() "
                "AND table_name=%s ORDER BY ordinal_position", (table,)).fetchall()]
            pk = [r[0] for r in self._run(
                "SELECT kcu.column_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                "AND tc.table_schema=kcu.table_schema WHERE tc.constraint_type='PRIMARY KEY' "
                "AND tc.table_schema=current_schema() AND tc.table_name=%s ORDER BY kcu.ordinal_position", (table,)).fetchall()]
            if not cols or not pk:
                raise sqlite3.OperationalError(f"no such table: {table}")
            self._info[table] = (cols, pk)
        return self._info[table]

    def _run(self, sql: str, params=()):
        with self._lock:
            try:
                return self._conn.execute(sql, params)
            except psycopg.OperationalError:
                if not self._conn.closed:
                    raise
                self._connect()                       # the pooler dropped an idle connection: reconnect once
                return self._conn.execute(sql, params)

    def execute(self, sql: str, params=()):
        return self._run(translate(sql, self._table_info), params)

    def executemany(self, sql: str, seq) -> None:
        for params in seq:
            self.execute(sql, params)

    def executescript(self, script: str) -> None:
        key = (self.url, self.schema, hashlib.md5(script.encode()).hexdigest())
        if key in _ready:
            return
        tables = []
        for stmt in (s.strip() for s in script.split(";")):
            if not stmt:
                continue
            self._run(translate_ddl(stmt))
            m = re.match(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", stmt, re.I)
            if m:
                tables.append(m.group(1))
        for t in tables:                              # Supabase serves tables through its REST API: lock them down
            self._run(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY')
        _ready.add(key)

    def commit(self) -> None:                         # autocommit: nothing to do
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        with self._lock:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()


def table_columns(conn, table: str) -> set[str]:
    if isinstance(conn, PgConnection):
        return {r[0] for r in conn._run("SELECT column_name FROM information_schema.columns WHERE table_schema="
                                        "current_schema() AND table_name=%s", (table,)).fetchall()}
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def connect(target, check_same_thread: bool = True):
    """A SQLite file or :memory:, or Postgres for a postgres:// URL."""
    target = str(target)
    test_url = os.environ.get("GATE0_TEST_DATABASE_URL", "")
    if test_url and not is_postgres(target):
        schema = "t_" + (uuid.uuid4().hex[:12] if target == ":memory:" else hashlib.md5(target.encode()).hexdigest()[:12])
        if (test_url, schema) not in test_schemas:
            test_schemas.append((test_url, schema))
        return PgConnection(test_url, schema)
    if is_postgres(target):
        return PgConnection(target)
    return sqlite3.connect(target, check_same_thread=check_same_thread)


def drop_test_schemas() -> None:
    """Removes the throwaway schemas a Postgres test run created."""
    for url, schema in test_schemas:
        try:
            conn = psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=15)
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            conn.close()
        except Exception:
            pass
    test_schemas.clear()
