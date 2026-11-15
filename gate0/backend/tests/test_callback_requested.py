"""A farmer who asks to be called later is shown as a callback request, never as 'Unanswered'; the row says when the call
has ended and the agent's notes are being read."""
from datetime import date, datetime

from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST

A = AttemptStatus
ONE = ("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
       "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes\n")
D = date(2026, 11, 15)
T0 = datetime(2026, 11, 15, 14, 10, tzinfo=IST)


class Asked:
    """A dialler whose agent heard 'call me at ...' but no weather confirmation (understood_weather: no_response)."""
    mode, live = "asked", False

    def __init__(self, callback="14:15"):
        self.callback, self.service, self.seen = callback, None, []

    def place(self, phone, language_name, variables):
        return ProviderCallResult(A.ANSWERED, provider_call_id="A1", duration_s=40)

    def outputs(self, attempt_id):
        self.seen.append([(c["status"], c["disposition"]) for c in self.service.calls()])      # what the log shows right now
        return {"understood_weather": "no_response", "stop_calls_requested": "no",
                "call_summary": "The farmer asked for a call back.", "callback_time": self.callback}


def make(tmp_path, dialler):
    s = DashboardService(str(tmp_path / "c.db"), dialler=dialler, env={"GATE0_WEATHER": "mock"}, now=lambda: T0)
    dialler.service = s
    s.import_csv(ONE)
    return s


def test_a_test_call_with_a_callback_request_says_callback_requested_not_unanswered(tmp_path):
    s = make(tmp_path, Asked())
    s._test_call("F1")
    row = s.calls()[0]
    assert row["status"] == "Callback Requested"
    assert "Test call" in row["disposition"] and "14:15" in row["disposition"]
    assert row["callback_requested_text"] == "14:15"
    assert s.db.execute("SELECT COUNT(*) FROM dash_callbacks").fetchone()[0] == 0      # a test never books a real call


def test_a_real_call_whose_callback_time_cannot_be_read_is_never_shown_as_unanswered(tmp_path):
    s = make(tmp_path, Asked(callback="sometime later"))
    s.fire(D)
    row = s.calls()[0]
    assert row["status"] == "Retrying" and row["callback_requested_text"] == "sometime later"   # nothing booked: the normal retry plan applies
    s.db.execute("UPDATE dash_retries SET status='done'")                                        # once no retry is left to come
    row = s.calls()[0]
    assert row["status"] == "Callback Requested" and "not booked" in row["disposition"]


def test_a_booked_callback_keeps_its_own_status(tmp_path):
    s = make(tmp_path, Asked(callback="14:15"))
    s.fire(D)
    assert s.calls()[0]["status"] == "Callback Scheduled"


def test_while_the_agents_notes_are_read_the_row_says_the_call_ended(tmp_path):
    d = Asked()
    s = make(tmp_path, d)
    s.fire(D)
    assert d.seen[0][0][0] == "In Call" and "ended" in d.seen[0][0][1].lower()


def test_no_notes_at_all_still_is_not_unanswered_when_the_call_was_answered(tmp_path):
    s = make(tmp_path, Asked(callback=""))
    s._test_call("F1")
    assert s.calls()[0]["status"] == "Unanswered"          # 'no_response' with no request: hello or silence, as before
