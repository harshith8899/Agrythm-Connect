"""A farmer who rings the number back: the inbound line is told who they are when we could not reach them, their call
is brought in as a result, and nobody is rung again right after calling us."""
import io
import json
from datetime import date, datetime, timedelta

from weathercall.adapters.dialers import SarvamDialler
from weathercall.adapters.mailer import RecordingMailer
from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST

A = AttemptStatus
CSV = ("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active,Email\n"
       "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes,\n")
D = date(2026, 11, 15)
T0 = datetime(2026, 11, 15, 9, 0, tzinfo=IST)


class Dial:
    """A dialler with an inbound line. place() answers as configured; find_inbound() returns the farmer's call-back."""
    mode, live = "t", False

    def __init__(self, status=A.NO_ANSWER, understood="", callback="", ready=True, fail_push=False):
        self.status, self.understood, self.callback = status, understood, callback
        self.inbound_ready, self.fail_push = ready, fail_push
        self.pushed, self.placed, self.found_args = [], 0, []
        self.inbound_call = None                      # (ProviderCallResult, ended at) once the farmer rings back
        self.inbound_out = {"understood_weather": "yes", "stop_calls_requested": "no", "call_summary": "s", "callback_time": ""}

    def place(self, phone, language_name, variables):
        self.placed += 1
        return ProviderCallResult(self.status, provider_call_id=f"OUT{self.placed}", duration_s=30 if self.status is A.ANSWERED else 0)

    def outputs(self, attempt_id):
        if attempt_id.startswith("IN"):
            return dict(self.inbound_out)
        return {"understood_weather": self.understood, "stop_calls_requested": "no", "call_summary": "s", "callback_time": self.callback}

    def push_inbound(self, phone, farmer_id, language_name, variables, cohort_name):
        if self.fail_push:
            raise RuntimeError("HTTP 500 +919876543210")
        self.pushed.append((phone, farmer_id, language_name, variables, cohort_name))
        return "c1"

    def find_inbound(self, phone, start, end, known_ids):
        self.found_args.append((phone, start, end, set(known_ids)))
        return self.inbound_call


def make(tmp_path, dial, now=T0):
    mail = RecordingMailer()
    s = DashboardService(str(tmp_path / "c.db"), dialler=dial, env={"GATE0_WEATHER": "mock", "GATE0_MAIL_TEST_TO": "t@x.org"},
                         now=lambda: now, mailer=mail)
    s.import_csv(CSV)
    s.ports = s._make_ports()
    return s, mail


def calls_back(dial, minutes=10, duration=60):
    dial.inbound_call = (ProviderCallResult(A.ANSWERED, provider_call_id="IN1", duration_s=duration), T0 + timedelta(minutes=minutes))


# ---- telling the inbound line -------------------------------------------------------------------------------------
def test_a_farmer_we_could_not_reach_is_told_to_the_inbound_line_once_with_their_weather(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    assert len(d.pushed) == 1
    phone, fid, lang, v, cohort = d.pushed[0]
    assert (phone, fid, lang, cohort) == ("9876543210", "F1", "Hindi", "back-2026-11-15-F1")
    saved = s._saved_weather("F1", D.isoformat())
    assert v["farmer_name"] == "Ramesh" and v["place_name"] == "Mandya" and v["temp_max_c"] == str(saved["temp_max"])
    assert "could not reach them" in v["callback_context"] and "calling us back" in v["callback_context"] and "now_text" not in v
    assert s.inbound()[0]["status"] == "waiting" and s.inbound()[0]["context"] == "missed"
    s.dialler.status = A.BUSY
    s._retry_one(s.ports, "F1", D, 2)                       # a second miss the same day: no second push
    assert len(d.pushed) == 1


def test_nothing_is_pushed_when_the_farmer_was_served_or_asked_for_a_callback_or_to_stop(tmp_path):
    cases = [Dial(A.ANSWERED, "yes"), Dial(A.ANSWERED, "declined"), Dial(A.ANSWERED, "no_response", callback="16:30"),
             Dial(A.FAILED), Dial(ready=False)]
    for n, d in enumerate(cases):
        (tmp_path / str(n)).mkdir()
        s, _ = make(tmp_path / str(n), d)
        s.fire_one("F1", D)
        assert d.pushed == [], n
    d = Dial(A.ANSWERED, "unclear")
    (tmp_path / "x").mkdir()
    s, _ = make(tmp_path / "x", d)
    s.fire_one("F1", D)
    assert len(d.pushed) == 1                               # heard but never confirmed: they may ring back


def test_a_farmer_without_consent_is_not_told_to_the_line(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.update_farmer("F1", {"call_consent": "No"})
    s.fire_one("F1", D)
    assert d.pushed == []


def test_a_failed_push_is_recorded_by_type_and_the_call_result_is_kept(tmp_path):
    d = Dial(fail_push=True)
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    assert s.inbound()[0]["status"] == "failed" and s.inbound()[0]["note"] == "RuntimeError"
    assert "9876" not in str(s.alerts()) and s.calls()[0]["status"]


def test_a_missed_callback_tells_the_line_about_the_requested_time(tmp_path):
    d = Dial(A.ANSWERED, "no_response", callback="14:15")
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    assert d.pushed == []                                   # a callback is booked: they wait for our call
    d.status, d.understood, d.callback = A.NO_ANSWER, "", ""
    s.run_due_callbacks(datetime(2026, 11, 15, 14, 16, tzinfo=IST))
    assert len(d.pushed) == 1 and "14:15" in d.pushed[0][3]["callback_context"]
    assert s.inbound()[0]["context"] == "callback 14:15"


# ---- bringing the call-back in --------------------------------------------------------------------------------------
def test_a_farmer_who_calls_back_and_understands_is_completed_and_not_rung_again(tmp_path):
    d = Dial()
    s, mail = make(tmp_path, d)
    s.fire_one("F1", D)                                     # not picked up: a retry is waiting for 09:30
    s._live_clear("F1")                                     # (the daily run clears the In Call row; fire_one alone does not)
    assert s.sync_inbound(T0 + timedelta(minutes=5)) == 0   # has not rung yet
    calls_back(d)
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    phone, start, end, known = d.found_args[-1]
    assert phone == "9876543210" and known == {"OUT1"} and start == T0
    call = s.calls()[0]
    assert call["status"] == "Completed"
    assert s.inbound()[0]["status"] == "called_back"
    assert s.run_due_retries(T0 + timedelta(minutes=40)) == 0 and d.placed == 1        # the waiting retry was dropped
    assert any("Weather update for Mandya" in m[1] for m in mail.sent)        # and the weather email goes out
    assert s.sync_inbound(T0 + timedelta(minutes=45)) == 0                              # counted once


def test_a_pending_callback_is_dropped_when_the_farmer_calls_back_first(tmp_path):
    d = Dial(A.ANSWERED, "no_response", callback="14:15")
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    s.dialler.status, s.dialler.callback = A.NO_ANSWER, ""
    d.pushed.clear()
    s._offer_callback_in("F1", D, s._saved_weather("F1", D.isoformat()))          # as if the line had been told
    calls_back(d, minutes=120)
    assert s.sync_inbound(T0 + timedelta(minutes=130)) == 1
    assert s.run_due_callbacks(datetime(2026, 11, 15, 14, 16, tzinfo=IST)) == 0
    assert s.callbacks()[0]["status"] == "skipped"


def test_a_farmer_who_calls_back_and_asks_for_another_time_gets_that_callback(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    calls_back(d)
    d.inbound_out = {"understood_weather": "no_response", "stop_calls_requested": "no", "call_summary": "s", "callback_time": "16:30"}
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    assert [c["status"] for c in s.callbacks()] == ["pending"] and s.callbacks()[0]["asked"] == "16:30"
    assert s.run_due_retries(T0 + timedelta(minutes=40)) == 0                     # the retry gives way to the requested time


def test_a_call_back_that_does_not_settle_things_keeps_the_retries(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    calls_back(d)
    d.inbound_out = {"understood_weather": "no_response", "stop_calls_requested": "no", "call_summary": "s", "callback_time": ""}
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    assert s.inbound()[0]["status"] == "waiting"
    assert s.run_due_retries(T0 + timedelta(minutes=40)) == 1                     # not served: the retry still goes ahead


def test_inbound_does_nothing_without_an_inbound_line(tmp_path):
    d = Dial(ready=False)
    s, _ = make(tmp_path, d)
    assert s.sync_inbound(T0) == 0 and d.found_args == []


def test_waiting_rows_from_an_earlier_day_expire(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    assert s.sync_inbound(T0 + timedelta(days=1)) == 0
    assert s.inbound()[0]["status"] == "expired"


# ---- the Sarvam calls ---------------------------------------------------------------------------------------------
ENV = {"SARVAM_ORG_ID": "o", "SARVAM_WORKSPACE_ID": "w", "SARVAM_APP_ID": "a", "SARVAM_CONNECTION_ID": "c",
       "SARVAM_AGENT_PHONE": "+910000000000", "SARVAM_AGENT_API_KEY": "k", "SARVAM_INBOUND_DEPLOYMENT_ID": "dep-1"}


class Opener:
    def __init__(self, reply):
        self.reply, self.requests = reply, []

    def __call__(self, req, timeout=0):
        self.requests.append((req.full_url, req.get_method(), json.loads(req.data) if req.data else None))
        return io.BytesIO(json.dumps(self.reply).encode())


def test_push_inbound_streams_a_cohort_to_the_inbound_deployment():
    op = Opener({"cohort_id": "coh-1"})
    d = SarvamDialler(env=ENV, opener=op)
    assert d.inbound_ready and d.push_inbound("9876543210", "F1", "Hindi", {"farmer_name": "Ramesh"}, "back-x") == "coh-1"
    url, method, body = op.requests[0]
    assert url.endswith("/scheduling/v1/orgs/o/workspaces/w/deployments/dep-1/cohorts/stream") and method == "POST"
    assert body == {"name": "back-x", "users": [{"user_phone_number": "+919876543210", "user_identifier": "F1",
                                                  "app_variables": {"farmer_name": "Ramesh"},
                                                  "app_overrides": {"initial_language_name": "Hindi"}}]}


def test_without_a_deployment_id_there_is_no_inbound_line():
    env = {k: v for k, v in ENV.items() if k != "SARVAM_INBOUND_DEPLOYMENT_ID"}
    assert SarvamDialler(env=env, opener=Opener({})).inbound_ready is False


def test_find_inbound_matches_the_number_and_skips_our_own_calls():
    items = [{"attempt_id": "OUT1", "user_contact_masked": "XXXXXX3210", "connectivity_status": "connected", "duration_in_seconds": 40,
              "attempted_at": "2026-11-15T03:40:00"},
             {"attempt_id": "OTHER", "user_contact_masked": "XXXXXX9999", "connectivity_status": "connected", "duration_in_seconds": 40,
              "attempted_at": "2026-11-15T03:41:00"},
             {"attempt_id": "IN1", "user_contact_masked": "XXXXXX3210", "connectivity_status": "connected", "duration_in_seconds": 90,
              "attempted_at": "2026-11-15T03:50:00"}]
    d = SarvamDialler(env=ENV, opener=Opener({"items": items}))
    res, ended = d.find_inbound("9876543210", T0, T0 + timedelta(hours=1), {"OUT1"})
    assert res.provider_call_id == "IN1" and res.status is A.ANSWERED and res.duration_s == 90
    assert ended == datetime(2026, 11, 15, 3, 51, 30, tzinfo=ended.tzinfo)
    assert d.find_inbound("9876543210", T0, T0 + timedelta(hours=1), {"OUT1", "IN1"}) is None
