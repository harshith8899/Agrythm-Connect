"""A call that was on the phone when the process stopped (a deploy, a restart): the result is fetched from Sarvam and saved, the
callback the farmer asked for is scheduled, and a restarting process lets its calls finish first."""
from datetime import date, datetime, timedelta, timezone

import pytest

from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST

A = AttemptStatus
HEAD = "Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
ONE = HEAD + "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes\n"
TWO = ONE + "F2,Savitha,9876543211,Mysuru,Mysuru,Karnataka,Kannada,Yes,Yes\n"
D = date(2026, 11, 5)
T0 = datetime(2026, 11, 5, 9, 0, tzinfo=IST)
ENDED = datetime(2026, 11, 5, 3, 31, tzinfo=timezone.utc)            # 09:01 India time


class Lost:
    """A dialler that must never place a call here: it only answers 'what happened to the call I lost?'."""
    mode, live = "lost", False

    def __init__(self, result=None, callback=""):
        self.result, self.callback, self.asked = result, callback, []

    def place(self, *a):
        raise AssertionError("recovery must not place a call")

    def find_call(self, phone, start, end):
        self.asked.append((phone[-4:], start, end))
        return self.result

    def outputs(self, attempt_id):
        return {"call_summary": "Busy, asked for a call.", "callback_time": self.callback, "understood_weather": "no_response",
                "stop_calls_requested": "no", "transcript": [{"speaker": "Agent", "text": "Hello"}, {"speaker": "Farmer", "text": "No"}]}


def found(callback=""):
    return Lost((ProviderCallResult(A.ANSWERED, provider_call_id="J1", duration_s=26), ENDED), callback)


def make(tmp_path, dialler, csv=ONE):
    clock = {"now": T0}
    s = DashboardService(str(tmp_path / "r.db"), dialler=dialler, env={"GATE0_WEATHER": "mock"}, now=lambda: clock["now"])
    s.import_csv(csv)
    return s, clock


def alerts(s):
    return s.db.execute("SELECT kind, farmer_id FROM dash_alerts ORDER BY id").fetchall()


def test_a_first_call_lost_in_a_restart_is_recovered_with_its_callback(tmp_path):
    d = found(callback="09:20")
    s, clock = make(tmp_path, d)
    s._live_set("F1", D, "daily", 1, "calling")
    clock["now"] = T0 + timedelta(minutes=7)
    assert s.recover_live() == 1
    row = s.calls()[0]
    assert (row["status"], row["call_id"]) == ("Callback Scheduled", f"F1-{D.isoformat()}")
    assert row["scheduled_callback_time"] == "05 Nov, 09:20 AM"
    assert row["summary"] and row["transcript"] and row["attempts_used"] == 1
    assert d.asked and d.asked[0][0] == "3210"                                       # looked up by the last 4 digits
    assert s.db.execute("SELECT COUNT(*) FROM dash_live").fetchone()[0] == 0


def test_a_call_that_is_less_than_6_minutes_old_is_left_alone(tmp_path):
    d = found()
    s, clock = make(tmp_path, d)
    s._live_set("F1", D, "daily", 1, "calling")
    clock["now"] = T0 + timedelta(minutes=5)                                         # may still be on the phone in another process
    assert s.recover_live() == 0 and d.asked == []
    assert s.calls()[0]["status"] == "In Call"


def test_recovering_twice_saves_one_result(tmp_path):
    s, clock = make(tmp_path, found())
    s._live_set("F1", D, "manual", 1, "calling")
    clock["now"] = T0 + timedelta(minutes=7)
    assert s.recover_live() == 1
    s._live_set("F1", D, "manual", 1, "calling")                                     # the same row left again
    clock["now"] = T0 + timedelta(minutes=14)
    assert s.recover_live() == 0
    assert len(s.calls()) == 1


def test_a_lost_test_call_comes_back_as_its_own_test_row_once(tmp_path):
    s, clock = make(tmp_path, found())
    s._live_set("F1", D, "test", 1, "calling")
    clock["now"] = T0 + timedelta(minutes=7)
    assert s.recover_live() == 1
    s._live_set("F1", D, "test", 1, "calling")
    clock["now"] = T0 + timedelta(minutes=14)
    assert s.recover_live() == 0
    rows = s.calls()
    assert len(rows) == 1 and rows[0]["is_test"] and rows[0]["call_id"].startswith("TEST1-")
    assert rows[0]["status"] == "Unanswered"


def test_a_call_the_provider_has_no_record_of_is_dropped_and_the_team_is_told(tmp_path):
    s, clock = make(tmp_path, Lost(None))
    s._live_set("F1", D, "daily", 1, "calling")
    clock["now"] = T0 + timedelta(minutes=7)
    assert s.recover_live() == 0
    assert alerts(s) == [("interrupted_call", "F1")] and s.calls() == []
    s._live_set("F1", D, "test", 1, "calling")                                       # a test call: nobody needs telling
    s.recover_live()
    assert alerts(s) == [("interrupted_call", "F1")]


def test_a_send_cut_short_is_reported_once_and_nobody_is_called(tmp_path):
    s, clock = make(tmp_path, Lost(None), TWO)
    for fid in ("F1", "F2"):
        s._live_set(fid, D, "daily", 1, "queued")
    clock["now"] = T0 + timedelta(minutes=7)
    assert s.recover_live() == 0
    assert alerts(s) == [("send_interrupted", "")]
    assert s.db.execute("SELECT COUNT(*) FROM dash_live").fetchone()[0] == 0
    assert "2 farmers" in s.alerts()[0]["text"]


def test_a_retry_with_its_own_claim_is_left_to_that_recovery(tmp_path):
    d = found()
    s, clock = make(tmp_path, d)
    s.db.execute("INSERT INTO dash_retries VALUES('F1',?,2,?,'calling',?)", (D.isoformat(), T0.isoformat(), T0.isoformat()))
    s.db.commit()
    s._live_set("F1", D, "retry", 2, "calling")
    clock["now"] = T0 + timedelta(minutes=7)
    assert s.recover_live() == 0 and d.asked == []


def test_a_restarting_process_starts_no_new_call(tmp_path):
    s, _ = make(tmp_path, Lost(None))
    s.draining = True
    with pytest.raises(ValueError, match="restarting"):
        s.manual_call("F1", "test")
    s.db.execute("INSERT INTO dash_settings VALUES('auto_dispatch','on')")
    s.db.commit()
    s._tick_once()                                                                   # nothing runs, nothing is dialled
    assert s.calls() == [] and s._get_setting("last_auto_run_date") == ""


def test_the_daily_send_stops_after_the_call_in_hand_when_the_process_is_stopping(tmp_path):
    class Stopping(Lost):
        def place(self, phone, language_name, variables):
            self.service.draining = True                                             # the host asks the process to stop mid-call
            return ProviderCallResult(A.ANSWERED, provider_call_id="J9", duration_s=30)

        def outputs(self, attempt_id):
            return {"call_summary": "Heard it.", "callback_time": "", "understood_weather": "yes", "stop_calls_requested": "no"}
    d = Stopping()
    s, _ = make(tmp_path, d, TWO)
    d.service = s
    s.fire(D)
    seen = {c["farmer_id"]: c["status"] for c in s.calls()}
    assert seen["F1"] == "Completed" and seen["F2"] == "In Queue"                   # F1 finished and saved; F2 waits for the restart


def test_wait_idle_returns_when_no_call_is_on_the_phone(tmp_path):
    s, _ = make(tmp_path, Lost(None))
    assert s.wait_idle(2) is True
    s._live_set("F1", D, "daily", 1, "calling")
    assert s.wait_idle(0.1) is False
