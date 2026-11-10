"""A call whose result was never saved because the process stopped mid-call (a restart, a crash) is recovered from the provider."""
from datetime import date, datetime, timedelta, timezone

from weathercall.adapters.sarvam_agent import SarvamAgentTelephony, _result_from
from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST
from tests.test_dashboard_service import A, ONE, Scripted, T0, D, make, timed  # noqa: F401


class Remembers(Scripted):
    """A dialler that can look a past call up, as Sarvam can."""

    def __init__(self, statuses=(), found=None, callback="", understood="yes"):
        super().__init__(statuses, callback_text=callback, understood=understood)
        self.found, self.lookups = found, []

    def find_call(self, phone, start, end):
        self.lookups.append((start, end))
        return self.found

    def outputs(self, attempt_id):
        out = super().outputs(attempt_id)
        out["callback_time"] = self.cb
        return out


def stuck_retry(tmp_path, dialler, claimed=T0 + timedelta(minutes=31, seconds=51)):
    """A farmer not picked up at 09:00, whose 09:31 retry was claimed ('calling') and then the process died."""
    s, clock = timed(tmp_path, dialler)
    s.import_csv(ONE)
    s.fire(D)                                                            # 09:00 not picked up: retry for 09:30 is waiting
    with s.lock:
        s.db.execute("UPDATE dash_retries SET status='calling', note=? WHERE farmer_id='F1'", (claimed.isoformat(),))
        s.db.commit()
    return s, clock


def call_ended(minute, second=0):
    return ProviderCallResult(AttemptStatus.ANSWERED, provider_call_id="X9", duration_s=22), \
        datetime(2026, 11, 5, 9, minute, second, tzinfo=IST).astimezone(timezone.utc)


def test_a_call_lost_to_a_restart_is_recovered_with_the_callback_the_farmer_asked_for(tmp_path):
    d = Remembers((A.NO_ANSWER,), found=call_ended(32, 30), callback="09:35", understood="no_response")
    s, clock = stuck_retry(tmp_path, d)
    clock["now"] = T0 + timedelta(minutes=50)                            # long after: the process came back
    assert s.recover_interrupted() == 1
    c = s.calls()[0]
    assert c["attempts_used"] == 2 and c["status"] == "Callback Scheduled"          # the second attempt is on the record
    assert c["scheduled_callback_time"] == "05 Nov, 09:35 AM"                      # counted from the call, not from the recovery
    assert c["callback_requested_text"] == "09:35" and c["understood_weather"] == "no_response"
    assert c["next_attempt_at"] is None                                            # a callback replaces the retry
    assert len(d.calls) == 1                                                       # recovery never dials anyone
    with s.lock:
        assert s.db.execute("SELECT status, note FROM dash_retries").fetchone() == ("done", "recovered after an interruption")


def test_the_recovered_callback_is_then_placed_like_any_other(tmp_path):
    d = Remembers((A.NO_ANSWER, A.ANSWERED), found=call_ended(32, 30), callback="09:35")
    s, clock = stuck_retry(tmp_path, d)
    clock["now"] = T0 + timedelta(minutes=45)                                      # the claim is over 10 minutes old; 09:35 was 10 min ago
    s.tick()
    assert len(d.calls) == 2                                                       # recovered, then the callback placed (inside the grace), once
    s.tick()
    assert len(d.calls) == 2


def test_a_missing_call_is_dropped_and_the_team_told_not_dialled_again(tmp_path):
    d = Remembers((A.NO_ANSWER,), found=None)
    s, clock = stuck_retry(tmp_path, d)
    clock["now"] = T0 + timedelta(minutes=50)
    assert s.recover_interrupted() == 0
    with s.lock:
        assert s.db.execute("SELECT status FROM dash_retries").fetchone()[0] == "dropped"
    assert [a["kind"] for a in s.alerts()] == ["interrupted_call"] and len(d.calls) == 1


def test_a_call_still_in_progress_is_left_alone(tmp_path):
    d = Remembers((A.NO_ANSWER,), found=call_ended(32))
    s, clock = stuck_retry(tmp_path, d)
    clock["now"] = T0 + timedelta(minutes=36)                                      # claimed 4 minutes ago: still on the phone
    assert s.recover_interrupted() == 0 and d.lookups == []
    with s.lock:
        assert s.db.execute("SELECT status FROM dash_retries").fetchone()[0] == "calling"


def test_a_callback_lost_to_a_restart_is_recovered(tmp_path):
    d = Remembers((A.ANSWERED,), found=call_ended(36), callback="")
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)                                                                      # 09:00 completed
    due = T0 + timedelta(minutes=35)
    s._schedule_callback("F1", D, "09:35", now=T0)
    with s.lock:
        s.db.execute("UPDATE dash_callbacks SET status='calling', note=?", ((due + timedelta(seconds=5)).isoformat(),))
        s.db.commit()
    clock["now"] = T0 + timedelta(minutes=55)
    assert s.recover_interrupted() == 1
    assert s.callbacks()[0]["status"] == "answered" and len(d.calls) == 1


def test_the_claim_time_is_written_when_a_retry_is_taken(tmp_path):
    d = Remembers((A.NO_ANSWER, A.ANSWERED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    seen = {}
    orig = s._retry_one

    def spy(*a, **k):
        with s.lock:
            seen["row"] = s.db.execute("SELECT status, note FROM dash_retries").fetchone()
        return orig(*a, **k)
    s._retry_one = spy
    clock["now"] = T0 + timedelta(minutes=31)
    s.run_due_retries()
    assert seen["row"][0] == "calling" and seen["row"][1].startswith("2026-11-05T09:31")


def test_sarvam_find_call_matches_on_the_last_four_digits_and_time():
    adapter = SarvamAgentTelephony.__new__(SarvamAgentTelephony)
    adapter.org, adapter.ws, adapter.app = "o", "w", "a"
    items = [
        {"attempt_id": "first", "attempted_at": "2026-11-05T03:30:08", "connectivity_status": "no_answer", "duration_in_seconds": 0,
         "user_contact_masked": "******3210", "failure_reason": "NO_FAILURE_REASON"},
        {"attempt_id": "other", "attempted_at": "2026-11-05T04:02:00", "connectivity_status": "connected", "duration_in_seconds": 40,
         "user_contact_masked": "******9999", "failure_reason": None},
        {"attempt_id": "mine", "attempted_at": "2026-11-05T04:02:05", "connectivity_status": "connected", "duration_in_seconds": 22.5,
         "user_contact_masked": "******3210", "failure_reason": "NO_FAILURE_REASON", "ended_by": "AGENT_ENDS"},
    ]
    asked = []
    adapter._request = lambda url, body=None: asked.append(url) or {"items": items[1:]}
    res, ended = adapter.find_call("9876543210", datetime(2026, 11, 5, 9, 29, tzinfo=IST), datetime(2026, 11, 5, 9, 52, tzinfo=IST))
    assert res.provider_call_id == "mine" and res.status is AttemptStatus.ANSWERED and res.duration_s == 22
    assert ended == datetime(2026, 11, 5, 4, 2, 27, tzinfo=timezone.utc)
    assert "start_datetime=2026-11-05T03%3A59%3A00" in asked[0]                     # IST window sent as UTC
    adapter._request = lambda url, body=None: {"items": []}
    assert adapter.find_call("9876543210", datetime(2026, 11, 5, 9, 29, tzinfo=IST), datetime(2026, 11, 5, 9, 52, tzinfo=IST)) is None
    assert _result_from({"connectivity_status": None}, "x") is None                 # no verdict yet: not a result
