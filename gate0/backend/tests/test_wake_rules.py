"""The Supabase wake rule (supabase/wake_rules.sql): when must the backend be awake?

Runs only against Postgres: set GATE0_TEST_DATABASE_URL (see docs/SUPABASE.md). The rule is installed into the test's own
throwaway schema, rows are written through the same connection, and the rule is asked at chosen moments.
"""
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from weathercall.adapters.dialers import MockDialler
from weathercall.service import DashboardService, IST

pytestmark = pytest.mark.skipif(not os.environ.get("GATE0_TEST_DATABASE_URL"), reason="needs Postgres (GATE0_TEST_DATABASE_URL)")
RULES = (Path(__file__).resolve().parents[2] / "supabase" / "wake_rules.sql").read_text(encoding="utf-8")
HEAD = "Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
TWO = (HEAD + "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes\nF2,Savitha,9876543211,Mysuru,Mysuru,Karnataka,Kannada,Yes,Yes\n")


def at(h, m, s=0):
    return datetime(2026, 11, 10, h, m, s, tzinfo=IST).isoformat()


@pytest.fixture
def world(tmp_path):
    svc = DashboardService(str(tmp_path / "w.db"), dialler=MockDialler(), env={"GATE0_WEATHER": "mock"},
                           now=lambda: datetime(2026, 11, 10, 9, 0, tzinfo=IST))
    conn = svc.db
    schema = conn.schema
    conn._run(RULES.replace("__SCHEMA__", schema))          # the whole file, as one script
    svc.import_csv(TWO)

    def needed(when):
        return conn._run(f"select {schema}.backend_needed(%s::timestamptz)", (when,)).fetchone()[0]

    def run(sql, params=()):
        conn._run(sql, params)
    return svc, needed, run


def test_nothing_to_do_means_no_wake_up(world):
    _, needed, _ = world
    assert needed(at(9, 0)) is None and needed(at(3, 0)) is None


def test_a_retry_wakes_the_backend_three_minutes_early_and_not_before(world):
    _, needed, run = world
    run("insert into dash_retries values('F1','2026-11-10',2,%s,'pending','')", (at(9, 31, 51),))
    assert needed(at(9, 28, 0)) is None                     # 3 min 51 s early: too soon
    assert needed(at(9, 29, 0)) == "retry due"              # 2 min 51 s early: wake now (a cold start takes about a minute)
    assert needed(at(9, 31, 51)) == "retry due" and needed(at(9, 40)) == "retry due"    # still wanted until it is dealt with
    for finished in ("done", "dropped", "missed", "superseded"):
        run("update dash_retries set status=%s", (finished,))
        assert needed(at(9, 40)) is None


def test_a_callback_the_farmer_asked_for_wakes_the_backend(world):
    _, needed, run = world
    run("insert into dash_callbacks(farmer_id, due_at, source_date, status, note, attempt_id, call_summary, understood_weather, "
        "requested_text, updated_at, reschedules) values('F1',%s,'2026-11-10','pending','','','','','16:30','',0)", (at(16, 30),))
    assert needed(at(16, 20)) is None and needed(at(16, 27, 30)) == "callback due" and needed(at(16, 31)) == "callback due"
    for finished in ("answered", "skipped", "missed"):
        run("update dash_callbacks set status=%s", (finished,))
        assert needed(at(16, 31)) is None


def test_the_daily_send_wakes_the_backend_only_when_auto_send_is_on(world):
    _, needed, run = world
    assert needed(at(8, 58)) is None                        # auto-send is off by default: never wake for the daily send
    run("insert into dash_settings values('auto_dispatch','on')")
    assert needed(at(8, 50)) is None                        # too early
    assert needed(at(8, 57, 30)) == "daily send due"
    assert needed(at(14, 0)) == "daily send due"            # backend was down: still wanted until it runs, inside the window
    assert needed(at(22, 30)) is None                       # after 22:00 the backend skips the day: no need to wake it
    run("insert into dash_settings values('last_auto_run_date','2026-11-09')")
    assert needed(at(9, 0)) == "daily send due"             # yesterday's run does not count


def test_while_the_daily_send_runs_the_backend_stays_awake_until_everyone_has_a_result(world):
    _, needed, run = world
    run("insert into dash_settings values('auto_dispatch','on')")
    run("insert into dash_settings values('last_auto_run_date','2026-11-10')")
    run("insert into dash_settings values('last_auto_run',%s)", (at(9, 0, 5),))
    assert needed(at(9, 10)) == "daily send running"          # nobody has a result yet
    run("insert into dash_results(farmer_id, call_date, status) values('F1','2026-11-10','answered')")
    assert needed(at(9, 20)) == "daily send running"          # one farmer still to do
    run("insert into dash_results(farmer_id, call_date, status) values('F2','2026-11-10','skipped')")
    assert needed(at(9, 30)) is None                          # everyone has a result
    run("delete from dash_results where farmer_id='F2'")
    assert needed(at(11, 30)) is None                         # a run started over 2 hours ago is not kept alive for ever


def test_farmers_who_are_never_called_do_not_keep_the_backend_awake(world):
    _, needed, run = world
    run("insert into dash_settings values('auto_dispatch','on')")
    run("insert into dash_settings values('last_auto_run_date','2026-11-10')")
    run("insert into dash_settings values('last_auto_run',%s)", (at(9, 0, 5),))
    run("insert into dash_results(farmer_id, call_date, status) values('F1','2026-11-10','answered')")
    run("update dash_farmers set consent=0 where farmer_id='F2'")
    assert needed(at(9, 20)) is None                          # F2 has not consented: no call, nothing to wait for
    run("update dash_farmers set consent=1, active=0 where farmer_id='F2'")
    assert needed(at(9, 20)) is None                          # inactive: same


def test_the_lead_time_fits_the_backends_grace_window(world):
    """A wake-up 3 minutes early (the rule) or a few minutes late (a cold start) is far inside what the backend allows."""
    from weathercall import service as module
    assert module.GRACE_MINUTES >= 10


# ---- System Status shows what the timer last did --------------------------------------------------------------------------------
def test_system_status_reports_the_wake_up_timer(world, monkeypatch):
    from weathercall import system as module
    from weathercall.system import SystemChecks
    monkeypatch.setattr(module, "is_postgres", lambda target: True)         # the test's data is in Postgres under a file name
    svc, _, run = world
    now = datetime(2026, 11, 10, 12, 0, tzinfo=IST)
    checks = SystemChecks(svc, usage=None, now=lambda: now, env={})
    assert "No wake-up has been needed yet" in checks._timer()["detail"]
    run("insert into wake_log(at, reason, note) values (%s, 'retry due', 'not configured: add the Vault secrets')", (at(11, 30),))
    c = checks._timer()
    assert c["status"] == "fail" and "Vault secrets" in c["detail"] and "retry due" in c["detail"]      # it needed to wake the backend and could not
    run("insert into wake_log(at, reason, request_id) values (%s, 'callback due', 7)", (at(11, 45),))
    c = checks._timer()
    assert c["status"] == "ok" and "10 Nov 11:45" in c["detail"] and "callback due" in c["detail"]
    run("delete from wake_log")
    run("insert into wake_log(at, reason, note) values (%s, 'retry due', 'not configured: add the Vault secrets')", (at(2, 0),))
    assert checks._timer()["status"] == "off"                                                           # an old attempt is not a live problem


def test_the_timer_check_is_left_out_without_postgres(tmp_path, monkeypatch):
    from weathercall import system as module
    monkeypatch.setattr(module, "is_postgres", lambda target: False)
    svc = DashboardService(str(tmp_path / "x.db"), dialler=MockDialler(), env={"GATE0_WEATHER": "mock"})
    assert module.SystemChecks(svc, usage=None, env={})._timer() is None
