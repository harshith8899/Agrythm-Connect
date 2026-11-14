"""A call is visible on the call log from the moment it is triggered: In Queue, then In Call, then its result."""
import sqlite3
from datetime import date, datetime, timedelta

from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST

A = AttemptStatus
HEAD = "Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
TWO = (HEAD + "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes\n"
       "F2,Savitha,9876543211,Mysuru,Mysuru,Karnataka,Kannada,Yes,Yes\n")
ONE = HEAD + "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes\n"
D = date(2026, 11, 5)
T0 = datetime(2026, 11, 5, 9, 0, tzinfo=IST)


class Watching:
    """A dialler that, while a call is being placed, looks at what the call log shows at that moment."""
    mode, live = "watching", False

    def __init__(self, statuses, boom=False):
        self.statuses, self.boom, self.service, self.seen = list(statuses), boom, None, []

    def place(self, phone, language_name, variables):
        self.seen.append({c["farmer_id"]: (c["status"], c["disposition"], c["call_id"], bool(c.get("is_test")))
                          for c in self.service.calls()})
        if self.boom:
            raise RuntimeError("provider down")
        return ProviderCallResult(self.statuses.pop(0), provider_call_id=f"A{len(self.seen)}", duration_s=30)

    def outputs(self, attempt_id):
        return {"understood_weather": "yes", "stop_calls_requested": "no", "call_summary": "", "callback_time": ""}


def make(tmp_path, dialler, clock=None, name="l.db"):
    clock = clock if clock is not None else {"now": T0}
    s = DashboardService(str(tmp_path / name), dialler=dialler, env={"GATE0_WEATHER": "mock"}, now=lambda: clock["now"])
    dialler.service = s
    return s, clock


def statuses(s):
    return {c["farmer_id"]: c["status"] for c in s.calls()}


def test_the_daily_send_shows_everyone_in_queue_then_each_one_in_call_then_the_result(tmp_path):
    d = Watching([A.ANSWERED, A.NO_ANSWER])
    s, _ = make(tmp_path, d)
    s.import_csv(TWO)
    s.fire(D)
    first, second = d.seen
    assert first["F1"][0] == "In Call" and first["F2"][0] == "In Queue"          # F1 is on the phone, F2 waits
    assert second["F1"][0] == "Completed" and second["F2"][0] == "In Call"      # F1 has its result, F2 is next
    assert "Calling now" in first["F1"][1] and "Waiting in the queue" in first["F2"][1]
    assert statuses(s) == {"F1": "Completed", "F2": "Retrying"}                  # nothing is left In Queue or In Call
    assert s.db.execute("SELECT COUNT(*) FROM dash_live").fetchone()[0] == 0


def test_the_live_row_and_the_result_are_one_row_with_the_same_id(tmp_path):
    d = Watching([A.ANSWERED])
    s, _ = make(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    during = d.seen[0]["F1"]
    assert during[2] == f"F1-{D.isoformat()}"
    assert [c["call_id"] for c in s.calls()] == [during[2]]                       # no duplicate row afterwards


def test_a_retry_shows_which_attempt_is_in_call_on_the_row_that_already_exists(tmp_path):
    d = Watching([A.NO_ANSWER, A.ANSWERED])
    s, clock = make(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    assert statuses(s) == {"F1": "Retrying"}
    clock["now"] = T0 + timedelta(minutes=30)
    assert s.run_due_retries() == 1
    status, disposition, call_id, _ = d.seen[1]["F1"]
    assert status == "In Call" and "attempt 2 of 3" in disposition
    assert [c["call_id"] for c in s.calls()] == [call_id]                         # still a single row for the farmer's day
    assert statuses(s) == {"F1": "Completed"}


def test_a_due_retry_is_in_queue_until_its_turn(tmp_path):
    d = Watching([A.NO_ANSWER, A.NO_ANSWER, A.ANSWERED, A.ANSWERED])
    s, clock = make(tmp_path, d)
    s.import_csv(TWO)
    s.fire(D)
    clock["now"] = T0 + timedelta(minutes=30)
    assert s.run_due_retries() == 2
    assert d.seen[2]["F1"][0] == "In Call" and d.seen[2]["F2"][0] == "In Queue"
    assert d.seen[3]["F2"][0] == "In Call"


def test_a_test_call_shows_as_its_own_in_call_row(tmp_path):
    d = Watching([A.ANSWERED])
    s, _ = make(tmp_path, d)
    s.import_csv(ONE)
    s._test_call("F1")
    status, disposition, call_id, is_test = d.seen[0]["F1"]
    assert (status, is_test) == ("In Call", True) and call_id.startswith("TEST-LIVE-") and "Test call" in disposition
    rows = s.calls()
    assert len(rows) == 1 and rows[0]["call_id"].startswith("TEST1-") and rows[0]["status"] == "Completed"


def test_a_call_that_cannot_be_placed_ends_as_failed_not_stuck_in_call(tmp_path):
    d = Watching([], boom=True)
    s, _ = make(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    assert d.seen[0]["F1"][0] == "In Call"
    row = s.calls()[0]
    assert row["status"] in ("Failed", "Retrying") and row["status"] != "In Call"
    assert s.db.execute("SELECT COUNT(*) FROM dash_live").fetchone()[0] == 0


def test_a_row_left_by_a_stopped_process_is_dropped_and_a_new_process_starts_clean(tmp_path):
    d = Watching([A.ANSWERED])
    s, clock = make(tmp_path, d)
    s.import_csv(ONE)
    s._live_set("F1", D, "daily", 1, "calling")
    assert statuses(s) == {"F1": "In Call"}
    clock["now"] = T0 + timedelta(minutes=21)                                    # nobody finished it: the process stopped
    assert statuses(s) == {}
    s._live_set("F1", D, "daily", 1, "queued")
    s2, _ = make(tmp_path, Watching([]), name="l.db")                            # a new process on the same database
    assert s2.db.execute("SELECT COUNT(*) FROM dash_live").fetchone()[0] == 0


def test_a_live_row_for_another_day_does_not_change_todays_result_row(tmp_path):
    d = Watching([A.ANSWERED])
    s, _ = make(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    s._live_set("F1", D + timedelta(days=1), "callback", 1, "calling")           # a callback tomorrow, on the phone now
    rows = {c["call_id"]: c["status"] for c in s.calls()}
    assert rows[f"F1-{D.isoformat()}"] == "Completed" and rows[f"F1-{(D + timedelta(days=1)).isoformat()}"] == "In Call"
