"""The inbound line: only registered farmers are known to it, each with what happened today, a farmer's call to us is
brought in as a result, and nobody is rung again right after calling us."""
import io
import json
from datetime import date, datetime, timedelta

from weathercall.adapters.dialers import SarvamDialler
from weathercall.adapters.mailer import RecordingMailer
from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST

A = AttemptStatus
CSV = ("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active,Email\n"
       "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes,\n"
       "F2,Lakshmi,9876543211,Mysuru,Mysuru,Karnataka,English,Yes,Yes,\n"
       "F3,Gopal,9876543212,Hassan,Hassan,Karnataka,Hindi,No,Yes,\n")
D = date(2026, 11, 15)
T0 = datetime(2026, 11, 15, 9, 0, tzinfo=IST)


class Dial:
    """A dialler with an inbound line. place() answers as configured; find_inbound_calls() returns what farmers rang."""
    mode, live = "t", False

    def __init__(self, status=A.NO_ANSWER, understood="", callback="", ready=True, fail_push=False):
        self.status, self.understood, self.callback = status, understood, callback
        self.inbound_ready, self.fail_push = ready, fail_push
        self.pushes, self.placed, self.calls_in, self.seen_known = [], 0, [], []
        self.inbound_out = {"understood_weather": "yes", "stop_calls_requested": "no", "call_summary": "s", "callback_time": ""}

    def place(self, phone, language_name, variables):
        self.placed += 1
        return ProviderCallResult(self.status, provider_call_id=f"OUT{self.placed}", duration_s=30 if self.status is A.ANSWERED else 0)

    def outputs(self, attempt_id):
        if attempt_id.startswith("IN"):
            return dict(self.inbound_out)
        return {"understood_weather": self.understood, "stop_calls_requested": "no", "call_summary": "s", "callback_time": self.callback}

    def push_inbound_many(self, entries, cohort_name):
        if self.fail_push:
            raise RuntimeError("HTTP 500 +919876543210")
        self.pushes.append((list(entries), cohort_name))
        return ["c1"]

    def find_inbound_calls(self, start, end, known_ids):
        self.seen_known.append(set(known_ids))
        return [c for c in self.calls_in if c[1].provider_call_id not in known_ids]

    def pushed(self, fid):
        """The latest entry pushed for a farmer."""
        return next((e for batch, _ in reversed(self.pushes) for e in batch if e["fid"] == fid), None)


def make(tmp_path, dial, now=T0, import_csv=True):
    mail = RecordingMailer()
    s = DashboardService(str(tmp_path / "c.db"), dialler=dial, env={"GATE0_WEATHER": "mock", "GATE0_MAIL_TEST_TO": "t@x.org"},
                         now=lambda: now, mailer=mail)
    s.async_inbound = False
    if import_csv:
        s.import_csv(CSV)
    s.ports = s._make_ports()
    return s, mail


def rings(dial, last4="3210", minutes=10, duration=60, attempt_id="IN1"):
    dial.calls_in.append((last4, ProviderCallResult(A.ANSWERED, provider_call_id=attempt_id, duration_s=duration),
                          T0 + timedelta(minutes=minutes)))


# ---- who may ring, and what the line says to each -------------------------------------------------------------------
def test_every_registered_farmer_is_told_to_the_line_and_a_farmer_without_consent_is_an_unknown_number(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)                                # the import already told the line
    f1, f2, f3 = d.pushed("F1"), d.pushed("F2"), d.pushed("F3")
    assert (f1["state"], f1["phone"], f1["language_name"]) == ("not_called", "9876543210", "Hindi")
    v = f1["variables"]
    assert v["farmer_name"] == "Ramesh" and v["place_name"] == "Mandya" and v["temp_max_c"] and "not called" not in v
    assert "have not called this farmer yet today" in v["callback_context"] and "now_text" not in v
    assert f2["variables"]["farmer_name"] == "Lakshmi"
    assert f3["state"] == "unregistered" and f3["variables"]["farmer_name"] == "" and f3["variables"]["callback_context"] == ""
    assert f3["variables"]["temp_max_c"] == ""              # nothing is given away about a number that may not ring


def test_only_a_changed_state_is_sent_again_and_force_sends_everyone(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    n = len(d.pushes)
    assert s._refresh_inbound() == 0 and len(d.pushes) == n                  # nothing changed
    assert s._refresh_inbound(force=True) == 3 and len(d.pushes) == n + 1


def test_the_state_follows_what_happens_to_the_farmer_today(tmp_path):
    d = Dial(A.NO_ANSWER, "")
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    assert d.pushed("F1")["state"] == "missed" and "could not reach them" in d.pushed("F1")["variables"]["callback_context"]
    d.status, d.understood = A.ANSWERED, "yes"
    s.fire_one("F2", D)
    assert d.pushed("F2")["state"] == "completed" and "they said they understood it" in d.pushed("F2")["variables"]["callback_context"]


def test_a_requested_callback_and_a_missed_one_each_have_their_own_state(tmp_path):
    d = Dial(A.ANSWERED, "no_response", callback="14:15")
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    e = d.pushed("F1")
    assert e["state"] == "callback 14:15" and "call back at 14:15" in e["variables"]["callback_context"]
    d.status, d.callback = A.NO_ANSWER, ""
    s.run_due_callbacks(datetime(2026, 11, 15, 14, 16, tzinfo=IST))
    e = d.pushed("F1")
    assert e["state"] == "callback_missed 14:15" and "we will not call again today" in e["variables"]["callback_context"]


def test_declined_and_stopped_farmers_have_their_own_state(tmp_path):
    d = Dial(A.ANSWERED, "declined")
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    assert d.pushed("F1")["state"] == "declined"
    s._note_stop("F2", D - timedelta(days=1))
    s._note_stop("F2", D)
    s._refresh_inbound(["F2"])
    assert d.pushed("F2")["state"] == "stopped" and d.pushed("F2")["variables"]["temp_max_c"] == ""


def test_a_farmer_who_loses_consent_or_is_made_inactive_becomes_an_unknown_number(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.update_farmer("F1", {"call_consent": "No"})
    assert d.pushed("F1")["state"] == "unregistered" and d.pushed("F1")["variables"]["farmer_name"] == ""
    s.update_farmer("F2", {"active": "No"})
    assert d.pushed("F2")["state"] == "unregistered"
    s.update_farmer("F2", {"active": "Yes"})                                 # registered again: known again
    assert d.pushed("F2")["state"] == "not_called" and d.pushed("F2")["variables"]["farmer_name"] == "Lakshmi"


def test_a_farmer_added_by_hand_is_known_to_the_line(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    new = s.add_farmer({"farmer_name": "Anil", "phone_number": "9876500000", "village": "Mandya", "preferred_language": "Hindi",
                        "call_consent": "Yes"})
    assert d.pushed(new["farmer_id"])["variables"]["farmer_name"] == "Anil"


def test_the_full_list_is_sent_once_a_day(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    n = len(d.pushes)
    s._daily_inbound_roster()
    s._daily_inbound_roster()
    assert len(d.pushes) == n + 1


def test_nothing_happens_without_an_inbound_line(tmp_path):
    d = Dial(ready=False)
    s, _ = make(tmp_path, d)
    assert d.pushes == [] and s.sync_inbound(T0) == 0 and d.seen_known == []


def test_a_failed_push_is_recorded_by_type_retried_and_never_stops_the_call_result(tmp_path):
    d = Dial(fail_push=True)
    s, _ = make(tmp_path, d)
    assert {r["status"] for r in s.inbound()} == {"failed"} and all(r["note"] == "RuntimeError" for r in s.inbound())
    assert "9876" not in str(s.alerts()) and any(a["kind"] == "inbound_push_failed" for a in s.alerts())
    d.fail_push = False
    assert s._refresh_inbound() == 3                                         # a failed row is tried again
    assert {r["status"] for r in s.inbound()} == {"waiting"}


# ---- bringing the call in -----------------------------------------------------------------------------------------
def test_a_farmer_who_calls_back_and_understands_is_completed_and_not_rung_again(tmp_path):
    d = Dial()
    s, mail = make(tmp_path, d)
    s.fire_one("F1", D)                                     # not picked up: a retry is waiting for 09:30
    s._live_clear("F1")
    assert s.sync_inbound(T0 + timedelta(minutes=5)) == 0
    rings(d)
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    assert "OUT1" in d.seen_known[-1]
    assert s.calls()[0]["status"] == "Completed" and d.pushed("F1")["state"] == "completed"
    assert s.run_due_retries(T0 + timedelta(minutes=40)) == 0 and d.placed == 1            # the waiting retry was dropped
    assert any("Weather update for Mandya" in m[1] for m in mail.sent)
    assert s.sync_inbound(T0 + timedelta(minutes=45)) == 0                                  # counted once


def test_calls_from_an_unknown_or_shared_number_are_ignored(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    rings(d, last4="9999", attempt_id="IN9")                # nobody has this number
    s.update_farmer("F2", {"phone_number": "9000003210"})   # now two farmers end in 3210
    rings(d, last4="3210", attempt_id="IN8")
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 0 and d.placed == 0


def test_a_farmer_who_rings_again_after_completing_keeps_their_result(tmp_path):
    d = Dial(A.ANSWERED, "yes")
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    s._live_clear("F1")
    d.inbound_out = {"understood_weather": "no", "stop_calls_requested": "no", "call_summary": "s", "callback_time": ""}
    rings(d, attempt_id="IN2")
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    assert s.calls()[0]["status"] == "Completed" and d.pushed("F1")["state"] == "completed"


def test_a_farmer_who_rings_before_the_daily_call_is_served_and_not_called_again_today(tmp_path):
    d = Dial(A.ANSWERED, "yes")
    s, _ = make(tmp_path, d)
    rings(d)
    assert s.sync_inbound(T0 + timedelta(minutes=5)) == 1
    assert s.calls()[0]["status"] == "Completed"
    s.fire_one("F1", D)
    assert d.placed == 0                                    # one call per farmer per day: already served


def test_a_pending_callback_is_dropped_when_the_farmer_calls_first_and_understands(tmp_path):
    d = Dial(A.ANSWERED, "no_response", callback="14:15")
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    s._live_clear("F1")
    rings(d, minutes=120)
    assert s.sync_inbound(T0 + timedelta(minutes=130)) == 1
    assert s.run_due_callbacks(datetime(2026, 11, 15, 14, 16, tzinfo=IST)) == 0
    assert s.callbacks()[0]["status"] == "skipped"


def test_a_farmer_who_calls_and_asks_for_another_time_gets_that_callback(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    s._live_clear("F1")
    rings(d)
    d.inbound_out = {"understood_weather": "no_response", "stop_calls_requested": "no", "call_summary": "s", "callback_time": "16:30"}
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    assert [c["status"] for c in s.callbacks()] == ["pending"] and s.callbacks()[0]["asked"] == "16:30"
    assert s.run_due_retries(T0 + timedelta(minutes=40)) == 0
    assert d.pushed("F1")["state"] == "callback 16:30"


def test_a_call_that_does_not_settle_things_keeps_the_retries(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)
    s._live_clear("F1")
    rings(d)
    d.inbound_out = {"understood_weather": "no_response", "stop_calls_requested": "no", "call_summary": "s", "callback_time": ""}
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    assert s.run_due_retries(T0 + timedelta(minutes=40)) == 1


def test_waiting_rows_from_an_earlier_day_expire(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    assert s.sync_inbound(T0 + timedelta(days=1)) == 0
    assert {r["status"] for r in s.inbound()} == {"expired"}


# ---- the Sarvam calls ---------------------------------------------------------------------------------------------
ENV = {"SARVAM_ORG_ID": "o", "SARVAM_WORKSPACE_ID": "w", "SARVAM_APP_ID": "a", "SARVAM_CONNECTION_ID": "c",
       "SARVAM_AGENT_PHONE": "+910000000000", "SARVAM_AGENT_API_KEY": "k", "SARVAM_INBOUND_DEPLOYMENT_ID": "dep-1"}


class Opener:
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def __call__(self, req, timeout=0):
        self.requests.append((req.full_url, req.get_method(), json.loads(req.data) if req.data else None))
        return io.BytesIO(json.dumps(self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]).encode())


def test_push_inbound_many_streams_a_cohort_to_the_inbound_deployment_in_chunks_of_1000():
    op = Opener({"cohort_id": "coh-1"})
    d = SarvamDialler(env=ENV, opener=op)
    entries = [{"fid": f"F{i}", "phone": f"98765{i:05d}", "language_name": "Hindi", "variables": {"farmer_name": f"n{i}"}} for i in range(1001)]
    assert d.inbound_ready and d.push_inbound_many(entries, "roster-x") == ["coh-1", "coh-1"]
    url, method, body = op.requests[0]
    assert url.endswith("/scheduling/v1/orgs/o/workspaces/w/deployments/dep-1/cohorts/stream") and method == "POST"
    assert body["name"] == "roster-x" and len(body["users"]) == 1000 and op.requests[1][2]["name"] == "roster-x-2"
    assert body["users"][0] == {"user_phone_number": "+919876500000",
                                "app_variables": {"farmer_name": "n0"}, "app_overrides": {"initial_language_name": "Hindi"}}
    assert all("user_identifier" not in u for u in body["users"])                # Sarvam refuses it for deployments


def test_without_a_deployment_id_there_is_no_inbound_line():
    env = {k: v for k, v in ENV.items() if k != "SARVAM_INBOUND_DEPLOYMENT_ID"}
    assert SarvamDialler(env=env, opener=Opener({})).inbound_ready is False


def test_find_inbound_calls_skips_our_own_calls_and_unanswered_ones_and_reads_every_page():
    page1 = {"items": [{"attempt_id": "OUT1", "user_contact_masked": "XXXXXX3210", "connectivity_status": "connected",
                        "duration_in_seconds": 40, "attempted_at": "2026-11-15T03:40:00"},
                       {"attempt_id": "NA", "user_contact_masked": "XXXXXX3211", "connectivity_status": "no_answer",
                        "duration_in_seconds": 0, "attempted_at": "2026-11-15T03:41:00"}], "next_page_uri": "x"}
    page2 = {"items": [{"attempt_id": "IN1", "user_contact_masked": "XXXXXX3210", "connectivity_status": "connected",
                        "duration_in_seconds": 90, "attempted_at": "2026-11-15T03:50:00"}]}
    d = SarvamDialler(env=ENV, opener=Opener(page1, page2))
    found = d.find_inbound_calls(T0, T0 + timedelta(hours=1), {"OUT1"})
    assert len(found) == 1 and found[0][0] == "3210" and found[0][1].provider_call_id == "IN1" and found[0][1].duration_s == 90
    assert found[0][2] == datetime(2026, 11, 15, 3, 51, 30, tzinfo=found[0][2].tzinfo)


def test_the_cohort_push_leaves_out_blank_values_shared_numbers_and_numbers_that_cannot_be_dialled():
    op = Opener({"cohort_id": "coh-1"})
    d = SarvamDialler(env=ENV, opener=op)
    entries = [
        {"fid": "F1", "phone": "9876543210", "language_name": "Hindi", "variables": {"farmer_name": "Ramesh", "temp_min_c": ""}},
        {"fid": "F2", "phone": "9876543210", "language_name": "Hindi", "variables": {"farmer_name": "Same number"}},   # shared
        {"fid": "F3", "phone": "FAKE-0003", "language_name": "Hindi", "variables": {"farmer_name": "Bad number"}},      # cannot be dialled
        {"fid": "F4", "phone": "9876543211", "language_name": "English", "variables": {"farmer_name": "", "callback_context": ""}},
    ]
    assert d.push_inbound_many(entries, "roster-x") == ["coh-1"]
    users = op.requests[0][2]["users"]
    assert [u["user_phone_number"] for u in users] == ["+919876543210", "+919876543211"]
    assert users[0]["app_variables"] == {"farmer_name": "Ramesh"}           # the blank value is not sent
    assert users[1]["app_variables"] == {}                                   # an unknown number carries no values at all
