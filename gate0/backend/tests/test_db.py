import sqlite3

import pytest

from weathercall import db
from weathercall.db import is_postgres, qmarks, translate, translate_ddl


def info(table):
    return {"dash_settings": (["key", "value"], ["key"]),
            "dash_retries": (["farmer_id", "call_date", "attempt_no", "due_at", "status", "note"],
                             ["farmer_id", "call_date", "attempt_no"])}[table]


def test_postgres_targets_are_recognised():
    assert is_postgres("postgresql://u:p@host:5432/postgres") and is_postgres("postgres://x")
    assert not is_postgres("weathercall.db") and not is_postgres(":memory:")


def test_question_marks_become_placeholders_and_percent_is_doubled():
    assert qmarks("SELECT * FROM t WHERE a=? AND b=?") == "SELECT * FROM t WHERE a=%s AND b=%s"
    assert qmarks("SELECT '?' FROM t WHERE x LIKE 'a%' AND y=?") == "SELECT '?' FROM t WHERE x LIKE 'a%%' AND y=%s"


def test_insert_or_ignore_does_nothing_on_a_clash():
    assert translate("INSERT OR IGNORE INTO dash_stops VALUES(?,?)") == "INSERT INTO dash_stops VALUES(%s,%s) ON CONFLICT DO NOTHING"


def test_insert_or_replace_updates_the_row_with_the_same_key():
    sql = translate("INSERT OR REPLACE INTO dash_settings VALUES(?,?)", info)
    assert sql == "INSERT INTO dash_settings(key, value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value"
    sql = translate("INSERT OR REPLACE INTO dash_retries VALUES(?,?,?,?,?,?)", info)
    assert "ON CONFLICT (farmer_id, call_date, attempt_no) DO UPDATE SET due_at=EXCLUDED.due_at, status=EXCLUDED.status, note=EXCLUDED.note" in sql
    sql = translate("INSERT OR REPLACE INTO dash_retries(farmer_id, call_date, attempt_no) VALUES(?,?,?)", info)
    assert sql.endswith("DO NOTHING") and "(farmer_id, call_date, attempt_no)" in sql      # only key columns given


def test_other_statements_only_change_placeholders():
    assert translate("UPDATE t SET a=? WHERE b=?") == "UPDATE t SET a=%s WHERE b=%s"
    assert translate("DELETE FROM t WHERE a=?") == "DELETE FROM t WHERE a=%s"


def test_schema_definitions_are_translated():
    ddl = translate_ddl("CREATE TABLE IF NOT EXISTS a(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, lat REAL, n INT, message_text TEXT)")
    assert "id BIGSERIAL PRIMARY KEY" in ddl and "lat DOUBLE PRECISION" in ddl and "n INT" in ddl
    assert 'name TEXT COLLATE "C"' in ddl and 'message_text TEXT COLLATE "C"' in ddl and "AUTOINCREMENT" not in ddl
    assert translate_ddl('x TEXT COLLATE "C"') == 'x TEXT COLLATE "C"'                       # not applied twice
    assert translate_ddl("(at TEXT, text TEXT, id INT)") == '(at TEXT COLLATE "C", text TEXT COLLATE "C", id INT)'   # a column named text


def test_a_bad_schema_name_is_refused():
    if db.psycopg is None:
        pytest.skip("psycopg is not installed")
    with pytest.raises(ValueError, match="schema name"):
        db.PgConnection("postgresql://u:p@localhost/x", schema='evil"; DROP SCHEMA public;--')


@pytest.mark.skipif(bool(__import__("os").environ.get("GATE0_TEST_DATABASE_URL")), reason="the suite is running on Postgres")
def test_sqlite_is_still_the_default():
    conn = db.connect(":memory:")
    assert isinstance(conn, sqlite3.Connection)
    conn.execute("CREATE TABLE t(a INT, b TEXT)")
    assert db.table_columns(conn, "t") == {"a", "b"}
    assert sqlite3.IntegrityError in db.IntegrityError and sqlite3.OperationalError in db.OperationalError
