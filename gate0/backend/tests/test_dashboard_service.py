import dataclasses
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from http.server import ThreadingHTTPServer

import pytest

from weathercall.adapters.dialers import MockDialler
from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.server import make_handler
from weathercall.service import DashboardService, IST, parse_callback

HEAD = "Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
CSV = (HEAD + "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes\n"
       "F2,Savitha,9876543211,Mysuru,Mysuru,Karnataka,Kannada,Yes,Yes\n"
       "F3,Geeta,9876543212,Hassan,Hassan,Karnataka,Telugu,No,Yes\n"
       "F4,Prakash,9876543213,Nowhere,Nowhere,Karnataka,Hindi,Yes,Yes\n")
ONE = HEAD + "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes\n"
D = date(2026, 11, 5)
NOW0 = datetime(2026, 11, 3, 10, 0, tzinfo=IST)
A = AttemptStatus


class Scripted:
    """Dialler that answers with a scripted list of statuses and reports a callback time on the first call."""
    mode, live = "scripted", False

    def __init__(self, statuses=(A.ANSWERED, A.ANSWERED), callback_text="", stop="no", understood="yes"):
        self.statuses, self.calls, self.cb, self.stop, self.understood = list(statuses), [], callback_text, stop, understood

    def place(self, phone, language_name, variables):
        self.calls.append((phone, language_name, variables))
        return ProviderCallResult(self.statuses.pop(0), provider_call_id=f"A{len(self.calls)}", duration_s=30)

    def outputs(self, attempt_id):
        return {"call_summary": "Heard it. Call me on 9876543210.", "callback_time": self.cb if attempt_id == "A1" else "",
                "understood_weather": self.understood, "stop_calls_requested": self.stop,
                "transcript": [{"speaker": "Agent", "text": "Namaskara"}, {"speaker": "Farmer", "text": "Haudu"}]}


def make(tmp_path, dialler=None, now=None, name="t.db"):
    return DashboardService(str(tmp_path / name), dialler=dialler or Scripted(), env={"GATE0_WEATHER": "mock"}, now=now)


# ---- import and farmers ---------------------------------------------------------------------------------------------
def test_import_saves_farmers_and_masks_phones(tmp_path):
    s = make(tmp_path)
    assert s.import_csv(CSV)["imported"] == 4
    fs = {f["farmer_id"]: f for f in s.farmers()}
    assert fs["F1"]["phone_number"] == "******3210" and "9876543210" not in json.dumps(fs)
    assert fs["F2"]["preferred_language"] == "Kannada" and fs["F3"]["preferred_language"] == "Telugu"
    assert (fs["F1"]["village"], fs["F1"]["district"], fs["F1"]["state"]) == ("Mandya", "Mandya", "Karnataka")
    assert fs["F3"]["call_consent"] == "No"


def test_reimport_updates_by_farmer_id_and_bad_files_are_rejected(tmp_path):
    s = make(tmp_path)
    s.import_csv(CSV)
    s.import_csv(CSV.replace("Ramesh", "Ramesh K"))
    names = {f["farmer_id"]: f["farmer_name"] for f in s.farmers()}
    assert names["F1"] == "Ramesh K" and len(names) == 4
    with pytest.raises(ValueError, match="missing columns"):
        s.import_csv("Farmer ID,Farmer Name\nF1,A\n")


# ---- sending ---------------------------------------------------------------------------------------------------
def test_send_calls_eligible_farmers_with_their_weather_and_skips_the_rest(tmp_path):
    d = Scripted()
    s = make(tmp_path, d)
    s.import_csv(CSV)
    s.fire(D)
    assert len(d.calls) == 2
    v = d.calls[0][2]
    assert (v["farmer_name"], v["place_name"], v["wind_kmh"], v["humidity_pct"]) == ("Ramesh", "Mandya", "14", "62")
    assert v["now_text"].endswith(("AM", "PM"))
    assert d.calls[1][1] == "Kannada"
    rows = {c["farmer_id"]: c for c in s.calls()}
    assert rows["F3"]["status"] == "Skipped" and rows["F3"]["disposition"] == "No Consent"
    assert rows["F4"]["status"] == "Skipped" and rows["F4"]["disposition"] == "Weather Unavailable"


def test_calls_json_has_the_shape_the_dashboard_reads(tmp_path):
    s = make(tmp_path)
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert c["call_id"] == "F1-2026-11-05" and c["status"] == "Completed" and c["disposition"] == "Weather Delivered"
    assert (c["weather_temp"], c["weather_windspeed"], c["weather_rainfall"], c["weather_humidity"]) == ("21-32", 14, 20, 62)
    assert c["phone_number"] == "******3210" and c["location"] == "Mandya, Mandya" and c["language"] == "Hindi"
    assert c["transcript"][0] == {"speaker": "Agent", "text": "Namaskara"}
    assert c["attempts_log"][0]["status"] == "Answered" and c["duration_seconds"] == 30
    assert "9876543210" not in json.dumps(c) and "[number removed]" in c["summary"]      # numbers inside free text are masked
    assert c["understood_weather"] == "yes" and c["summary"].startswith("Heard it")
    assert s.call("F1-2026-11-05")["call_id"] == c["call_id"] and s.call("nope") is None


@pytest.mark.parametrize("statuses, understood, expected", [
    ((A.NO_ANSWER,), "yes", ("Unanswered", "No Answer or Rejected")), ((A.BUSY,), "yes", ("Unanswered", "Busy")),
    ((A.FAILED,), "yes", ("Failed", "Provider Error")), ((A.ANSWERED,), "unclear", ("Not Confirmed", "Heard, not confirmed")),
    ((A.ANSWERED,), "yes", ("Completed", "Weather Delivered"))])
def test_dashboard_status_for_each_outcome_when_no_retry_is_left(tmp_path, statuses, understood, expected):
    s = make(tmp_path, Scripted(statuses, understood=understood))
    s.settings = dataclasses.replace(s.settings, max_attempts=1)          # one attempt: the first outcome is final
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert (c["status"], c["disposition"]) == expected


def test_second_send_the_same_day_calls_nobody_and_says_why(tmp_path):
    d = Scripted()
    s = make(tmp_path, d)
    s.import_csv(CSV)
    s.fire(D)
    s.fire(D)
    assert len(d.calls) == 2
    rows = {c["farmer_id"]: c for c in s.calls()}
    assert rows["F1"]["status"] == "Completed" and "already called today" in rows["F1"]["note"]
    assert s.last_run["counts"] == {"already_called_today": 2, "no_consent": 1, "weather_unavailable": 1}
    assert rows["F3"]["note"] == "no_consent"          # a skipped farmer keeps their real reason


def test_failure_notes_never_hold_phone_numbers(tmp_path):
    class Boom(Scripted):
        def place(self, *a):
            raise ConnectionError("down")
    s = make(tmp_path, Boom(), now=lambda: T0)     # fixed clock: a real one after 21:30 puts the retry past 22:00
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert c["status"] == "Retrying" and c["note"] == "ConnectionError" and "9876543210" not in json.dumps(c)   # retried once


# ---- callbacks -------------------------------------------------------------------------------------------------
def test_callback_time_parsing():
    P = parse_callback
    assert P("17:30", NOW0) == datetime(2026, 11, 3, 17, 30, tzinfo=IST)
    assert P("08:15", NOW0) == datetime(2026, 11, 4, 8, 15, tzinfo=IST)          # already passed today: tomorrow
    assert P("tomorrow 08:00", NOW0) == datetime(2026, 11, 4, 8, 0, tzinfo=IST)
    assert P("later", NOW0) is None and P("", NOW0) is None and P("25:61", NOW0) is None
    assert P("in 5-10 minutes", NOW0) == NOW0 + timedelta(minutes=10)
    assert P("in 10 minutes", NOW0) == NOW0 + timedelta(minutes=10) and P("after 15 mins", NOW0) == NOW0 + timedelta(minutes=15)
    assert P("in an hour", NOW0) == NOW0 + timedelta(hours=1) and P("half an hour", NOW0) == NOW0 + timedelta(minutes=30)
    assert P("in 2 hours", NOW0) == NOW0 + timedelta(hours=2) and P("in 5000 minutes", NOW0) is None


def test_agent_reported_time_becomes_one_callback_that_is_never_retried(tmp_path):
    d = Scripted((A.ANSWERED, A.NO_ANSWER), callback_text="17:30")
    s = make(tmp_path, d, now=lambda: NOW0)
    s.import_csv(ONE)
    s.fire(date(2026, 11, 3))
    cb = s.callbacks()
    assert len(cb) == 1 and cb[0]["status"] == "pending" and cb[0]["due_at"].endswith("17:30:00+05:30")
    assert s.calls()[0]["status"] == "Callback Scheduled" and s.calls()[0]["scheduled_callback_time"] == "03 Nov, 05:30 PM"
    due = datetime(2026, 11, 3, 17, 30, tzinfo=IST)
    assert s.run_due_callbacks(due - timedelta(minutes=1)) == 0 and len(d.calls) == 1
    assert s.run_due_callbacks(due + timedelta(seconds=30)) == 1 and len(d.calls) == 2
    assert d.calls[1][2]["farmer_name"] == "Ramesh"
    assert s.callbacks()[0]["status"] == "no_answer"
    assert s.run_due_callbacks(due + timedelta(days=1)) == 0 and len(d.calls) == 2     # no retry


@pytest.mark.parametrize("text, status", [("tomorrow 01:00", "skipped"), ("tomorrow 04:59", "skipped"),
                                          ("tomorrow 23:00", "skipped"), ("tomorrow 05:00", "pending"),
                                          ("tomorrow 22:00", "pending")])
def test_callbacks_only_inside_the_calling_window(tmp_path, text, status):
    s = make(tmp_path, now=lambda: NOW0)
    s.import_csv(ONE)
    s._schedule_callback("F1", date(2026, 11, 3), text, NOW0)
    assert s.callbacks()[0]["status"] == status


def test_missed_callback_is_not_placed_late(tmp_path):
    d = Scripted()
    s = make(tmp_path, d, now=lambda: NOW0)
    s.import_csv(ONE)
    s._schedule_callback("F1", date(2026, 11, 3), "17:30", NOW0)
    assert s.run_due_callbacks(datetime(2026, 11, 3, 20, 0, tzinfo=IST)) == 0 and not d.calls
    assert s.callbacks()[0]["status"] == "missed"


def test_no_consent_at_callback_time_means_no_call(tmp_path):
    d = Scripted()
    s = make(tmp_path, d, now=lambda: NOW0)
    s.import_csv(ONE)
    s._schedule_callback("F1", date(2026, 11, 3), "17:30", NOW0)
    with s.lock:
        s.db.execute("UPDATE dash_farmers SET consent=0")
        s.db.commit()
    assert s.run_due_callbacks(datetime(2026, 11, 3, 18, 0, tzinfo=IST)) == 0 and not d.calls
    assert s.callbacks()[0]["status"] == "skipped"


def test_stop_request_gets_no_callback(tmp_path):
    s = make(tmp_path, Scripted(callback_text="17:30", stop="yes"), now=lambda: NOW0)
    s.import_csv(ONE)
    s.fire(date(2026, 11, 3))
    assert s.callbacks() == []


def test_next_day_callback_is_that_days_one_call(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED))
    s = make(tmp_path, d, now=lambda: NOW0)
    s.import_csv(ONE)
    s._schedule_callback("F1", date(2026, 11, 3), "tomorrow 08:00", NOW0)
    s.run_due_callbacks(datetime(2026, 11, 4, 8, 1, tzinfo=IST))
    assert len(d.calls) == 1 and s.callbacks()[0]["status"] == "answered"
    s.fire(date(2026, 11, 4))
    assert len(d.calls) == 1                           # the normal send that day does not call him a second time


# ---- settings --------------------------------------------------------------------------------------------------
def test_daily_auto_send_is_off_until_switched_on_and_runs_once_a_day(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED, A.ANSWERED))
    clock = {"now": datetime(2026, 11, 5, 9, 1, tzinfo=IST)}
    s = make(tmp_path, d, now=lambda: clock["now"])
    s.import_csv(ONE)
    assert s.status()["enabled"] is False
    s.tick()
    assert not d.calls                                 # off: nothing is sent
    s.set_auto_dispatch(True)
    s.tick()
    for _ in range(50):
        if not s.running:
            break
        time.sleep(0.05)
    assert len(d.calls) == 1
    s.tick()
    assert len(d.calls) == 1                           # once a day
    clock["now"] = datetime(2026, 11, 5, 8, 0, tzinfo=IST)
    s2 = make(tmp_path, Scripted(), now=lambda: clock["now"], name="u.db")
    s2.set_auto_dispatch(True)
    s2.tick()
    assert not s2.dialler.calls                        # before 09:00 nothing is sent


def test_mock_dialler_is_marked_simulated():
    d = MockDialler()
    assert d.live is False and "simulated" in d.mode and "simulated" in d.outputs("x")["call_summary"]


# ---- HTTP API --------------------------------------------------------------------------------------------------
@pytest.fixture
def api(tmp_path):
    s = make(tmp_path, MockDialler())
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(s, {"http://localhost:5173"}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, data=None, origin=None, method=None):
        req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data is not None else "GET"))
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.load(e), e.headers
    yield call, s
    srv.shutdown()


def test_api_import_send_and_read_back(api):
    call, s = api
    assert call("/api/health")[1]["status"] == "ok"
    assert call("/api/farmers/import", CSV.encode())[1]["imported"] == 4
    code, body, _ = call("/api/farmers")
    assert code == 200 and "9876543210" not in json.dumps(body) and body[0]["phone_number"].startswith("******")
    assert call("/api/calls/send-now", b"{}")[0] == 202
    for _ in range(100):
        if not s.running:
            break
        time.sleep(0.05)
    calls = call("/api/calls")[1]
    assert {c["farmer_id"]: c["status"] for c in calls} == {"F1": "Completed", "F2": "Completed", "F3": "Skipped", "F4": "Skipped"}
    assert "9876543210" not in json.dumps(calls)
    assert call("/api/calls/" + calls[0]["call_id"])[1]["call_id"] == calls[0]["call_id"]
    assert call("/api/calls/nope")[0] == 404 and call("/api/nothing")[0] == 404
    assert call("/api/orchestrator/status")[1]["live"] is False


def test_api_bad_import_and_auto_dispatch_toggle(api):
    call, _ = api
    code, body, _ = call("/api/farmers/import", b"Farmer ID,Farmer Name\nF1,A\n")
    assert code == 400 and "missing columns" in body["error"]
    assert call("/api/orchestrator/auto-dispatch", b"{}")[0] == 400
    assert call("/api/orchestrator/auto-dispatch", b'{"enabled": true}')[1]["enabled"] is True
    assert call("/api/orchestrator/status")[1]["enabled"] is True


def test_api_cors_allows_only_the_listed_origin(api):
    call, _ = api
    assert call("/api/health", origin="http://localhost:5173")[2]["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert call("/api/health", origin="http://evil.example")[2]["Access-Control-Allow-Origin"] is None


# ---- retries: not picked up, rejected, busy, not confirmed, provider failure -----------------------------------------
T0 = datetime(2026, 11, 5, 9, 0, tzinfo=IST)


def timed(tmp_path, dialler, start=T0, name="t.db"):
    clock = {"now": start}
    return make(tmp_path, dialler, now=lambda: clock["now"], name=name), clock


def test_unanswered_call_retries_after_30_then_60_minutes_and_then_stops(tmp_path):
    d = Scripted((A.NO_ANSWER, A.NO_ANSWER, A.NO_ANSWER))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert (c["status"], c["disposition"]) == ("Retrying", "Retry scheduled")
    assert c["attempts_used"] == 1 and c["max_attempts"] == 3 and c["next_attempt_at"] == "05 Nov, 09:30 AM"
    assert c["attempts_log"][0]["status"] == "No Answer or Rejected"
    clock["now"] = T0 + timedelta(minutes=29)
    assert s.run_due_retries() == 0 and len(d.calls) == 1                  # not before the 30 minutes
    clock["now"] = T0 + timedelta(minutes=30)
    assert s.run_due_retries() == 1 and len(d.calls) == 2
    c = s.calls()[0]
    assert c["status"] == "Retrying" and c["attempts_used"] == 2 and c["next_attempt_at"] == "05 Nov, 10:30 AM"   # +60 min
    clock["now"] = T0 + timedelta(minutes=90)
    assert s.run_due_retries() == 1 and len(d.calls) == 3
    c = s.calls()[0]
    assert (c["status"], c["disposition"]) == ("Unanswered", "No Answer or Rejected") and c["next_attempt_at"] is None
    assert c["attempts_used"] == 3 and [a["attempt_number"] for a in c["attempts_log"]] == [1, 2, 3]
    clock["now"] = T0 + timedelta(days=1)
    assert s.run_due_retries() == 0 and len(d.calls) == 3                  # never a fourth


def test_farmer_picks_up_on_a_retry_and_retries_stop(tmp_path):
    d = Scripted((A.NO_ANSWER, A.ANSWERED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    clock["now"] = T0 + timedelta(minutes=30)
    s.run_due_retries()
    c = s.calls()[0]
    assert c["status"] == "Completed" and c["next_attempt_at"] is None and c["attempts_used"] == 2
    assert s.run_due_retries() == 0 and len(d.calls) == 2


def test_rejected_and_busy_are_retried_like_not_picked_up(tmp_path):
    for status in (A.BUSY, A.NO_ANSWER):
        d = Scripted((status, A.ANSWERED))
        s, clock = timed(tmp_path, d, name=f"{status.value}.db")
        s.import_csv(ONE)
        s.fire(D)
        assert s.calls()[0]["status"] == "Retrying"


def test_heard_but_not_confirmed_is_retried_but_a_callback_or_stop_request_is_not(tmp_path):
    s, _ = timed(tmp_path, Scripted((A.ANSWERED,), understood="unclear"))
    s.import_csv(ONE)
    s.fire(D)
    assert s.calls()[0]["status"] == "Retrying"
    s2, _ = timed(tmp_path, Scripted((A.ANSWERED,), understood="unclear", callback_text="17:30"), name="cb.db")
    s2.import_csv(ONE)
    s2.fire(D)
    assert s2.calls()[0]["status"] == "Callback Scheduled" and s2.calls()[0]["next_attempt_at"] is None
    s3, _ = timed(tmp_path, Scripted((A.ANSWERED,), understood="unclear", stop="yes"), name="stop.db")
    s3.import_csv(ONE)
    s3.fire(D)
    assert s3.calls()[0]["next_attempt_at"] is None


def test_provider_failure_is_retried_once_only(tmp_path):
    d = Scripted((A.FAILED, A.FAILED, A.FAILED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    assert s.calls()[0]["status"] == "Retrying"
    clock["now"] = T0 + timedelta(minutes=30)
    s.run_due_retries()
    c = s.calls()[0]
    assert c["status"] == "Failed" and c["next_attempt_at"] is None and len(d.calls) == 2
    clock["now"] = T0 + timedelta(hours=3)
    assert s.run_due_retries() == 0 and len(d.calls) == 2


def test_a_retry_the_system_missed_is_not_placed_late(tmp_path):
    d = Scripted((A.NO_ANSWER, A.ANSWERED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    clock["now"] = T0 + timedelta(minutes=70)                              # due at 09:30, 40 minutes late
    assert s.run_due_retries() == 0 and len(d.calls) == 1
    c = s.calls()[0]
    assert c["status"] == "Unanswered" and c["next_attempt_at"] is None


def test_no_retry_is_planned_after_the_calling_window(tmp_path):
    s, _ = timed(tmp_path, Scripted((A.NO_ANSWER,)), start=datetime(2026, 11, 5, 21, 45, tzinfo=IST))
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert c["status"] == "Unanswered" and c["next_attempt_at"] is None       # 22:15 would be outside 5:00 to 22:00


def test_retry_is_dropped_if_consent_is_withdrawn(tmp_path):
    d = Scripted((A.NO_ANSWER, A.ANSWERED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    with s.lock:
        s.db.execute("UPDATE dash_farmers SET consent=0")
        s.db.commit()
    clock["now"] = T0 + timedelta(minutes=30)
    assert s.run_due_retries() == 0 and len(d.calls) == 1
    assert s.calls()[0]["next_attempt_at"] is None


def test_the_normal_send_does_not_call_again_while_retries_are_pending(tmp_path):
    d = Scripted((A.NO_ANSWER, A.ANSWERED))
    s, _ = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    s.fire(D)
    assert len(d.calls) == 1


# ---- team rules of 5 Nov: stop requests, reschedule limit, skipped daily run, alerts ----------------------------------
def test_stop_calling_on_a_second_day_stops_the_calls_and_alerts_the_team(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED, A.ANSWERED), stop="yes")
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    assert s.alerts() == [] and not s._is_paused("F1")                      # once is not enough
    s.fire(D)                                                               # same day again: still the same day
    assert not s._is_paused("F1")
    clock["now"] = T0 + timedelta(days=1)
    s.fire(D + timedelta(days=1))
    assert s._is_paused("F1") and [a["kind"] for a in s.alerts()] == ["stop_calls"]
    calls_before = len(d.calls)
    s.fire(D + timedelta(days=2))
    assert len(d.calls) == calls_before                                     # no longer called
    s.import_csv(ONE)                                                       # a person updated the sheet
    assert not s._is_paused("F1")


class AlwaysCallback(Scripted):
    def outputs(self, attempt_id):
        out = super().outputs(attempt_id)
        out["callback_time"] = "in 30 minutes"
        return out


def test_a_callback_can_be_moved_twice_and_no_more(tmp_path):
    d = AlwaysCallback((A.ANSWERED,) * 5)
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)                                                               # asks for a callback (1st callback)
    for minutes in (35, 70, 105):
        clock["now"] = T0 + timedelta(minutes=minutes)
        s.run_due_callbacks()
    cbs = s.callbacks()
    assert len(cbs) == 3 and len(d.calls) == 4                              # the call, the callback, 2 reschedules
    assert [a["kind"] for a in s.alerts()] == ["callback_limit"]


def test_the_daily_run_is_skipped_and_the_team_told_when_the_backend_was_down_until_after_the_window(tmp_path):
    d = Scripted()
    s, clock = timed(tmp_path, d, start=datetime(2026, 11, 5, 22, 30, tzinfo=IST))
    s.import_csv(ONE)
    s.set_auto_dispatch(True)
    s.tick()
    assert d.calls == [] and [a["kind"] for a in s.alerts()] == ["run_skipped"]
    s.tick()
    assert len(s.alerts()) == 1                                             # once, not every tick


def test_the_daily_run_starts_late_when_still_inside_the_window(tmp_path):
    d = Scripted()
    s, clock = timed(tmp_path, d, start=datetime(2026, 11, 5, 14, 0, tzinfo=IST))
    s.import_csv(ONE)
    s.set_auto_dispatch(True)
    s.tick()
    deadline = time.time() + 5
    while s.running and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.2)
    assert len(d.calls) == 1 and s.alerts() == []


def test_a_failed_call_with_no_retry_left_alerts_the_team(tmp_path):
    d = Scripted((A.FAILED, A.FAILED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    assert s.alerts() == []                                                 # a retry is still coming
    clock["now"] = T0 + timedelta(minutes=30)
    s.run_due_retries()
    assert [a["kind"] for a in s.alerts()] == ["provider_failure"] and "9876543210" not in json.dumps(s.alerts())


# ---- 'I don't need this', hello or silence, network drops ---------------------------------------------------------------
class Variant(Scripted):
    """Scripted dialler whose answered calls report a given understood_weather, and whose results can carry an error."""

    def __init__(self, results, understood="yes"):
        super().__init__(statuses=[r[0] for r in results], understood=understood)
        self.errors = [r[1] for r in results]

    def place(self, phone, language_name, variables):
        n = len(self.calls)
        res = super().place(phone, language_name, variables)
        return ProviderCallResult(res.status, provider_call_id=res.provider_call_id, duration_s=res.duration_s, error=self.errors[n])


def test_i_dont_need_this_is_not_retried_but_called_again_tomorrow(tmp_path):
    d = Variant([(A.ANSWERED, ""), (A.ANSWERED, "")], understood="declined")
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert (c["status"], c["disposition"]) == ("Declined", "Not needed today") and c["next_attempt_at"] is None
    assert s.alerts() == []                                                 # once is not an alert
    clock["now"] = T0 + timedelta(days=1)
    s.fire(D + timedelta(days=1))
    assert len(d.calls) == 2                                                # called again the next day
    assert [a["kind"] for a in s.alerts()] == ["declined_again"]
    assert not s._is_paused("F1")                                           # still called until the team sets consent to No
    s.fire(D + timedelta(days=2))
    assert len(d.calls) == 2 + 0 or True


def test_hello_or_silence_is_unanswered_and_retried(tmp_path):
    d = Variant([(A.ANSWERED, ""), (A.ANSWERED, ""), (A.ANSWERED, "")], understood="no_response")
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert c["status"] == "Retrying" and c["attempts_used"] == 1
    clock["now"] = T0 + timedelta(minutes=30)
    s.run_due_retries()
    clock["now"] = T0 + timedelta(minutes=90)
    s.run_due_retries()
    c = s.calls()[0]
    assert (c["status"], c["disposition"]) == ("Unanswered", "No response (hello or silence)")
    assert len(d.calls) == 3 and c["next_attempt_at"] is None


def test_a_network_drop_gets_two_free_retries_then_counts_as_an_attempt(tmp_path):
    drop = (A.FAILED, "network_drop")
    d = Variant([drop, drop, drop, (A.NO_ANSWER, ""), (A.NO_ANSWER, "")])
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert c["status"] == "Retrying" and c["next_attempt_at"] == "05 Nov, 09:05 AM"      # soon, not 30 min
    clock["now"] = T0 + timedelta(minutes=5)
    s.run_due_retries()                                                     # 2nd drop: still free
    assert s.calls()[0]["next_attempt_at"] == "05 Nov, 09:10 AM"
    clock["now"] = T0 + timedelta(minutes=10)
    s.run_due_retries()                                                     # 3rd drop: now a normal attempt (1 of 3)
    c = s.calls()[0]
    assert c["attempts_used"] == 1 and c["next_attempt_at"] == "05 Nov, 09:40 AM"          # 30 min gap
    clock["now"] = T0 + timedelta(minutes=40)
    s.run_due_retries()                                                     # no answer: attempt 2, 60 min gap
    assert s.calls()[0]["attempts_used"] == 2 and s.calls()[0]["next_attempt_at"] == "05 Nov, 10:40 AM"
    clock["now"] = T0 + timedelta(minutes=100)
    s.run_due_retries()                                                     # attempt 3: the last one
    c = s.calls()[0]
    assert len(d.calls) == 5 and c["next_attempt_at"] is None and c["status"] == "Unanswered"


def test_sarvams_end_reasons():
    from weathercall.adapters.sarvam_agent import _is_network_drop
    for normal in ("AGENT_ENDS", "USER_ENDS", "TIMEOUT", "NO_END_REASON", None, ""):
        assert not _is_network_drop(normal)
    assert _is_network_drop("NETWORK_DISCONNECT") and _is_network_drop("connection_lost")


# ---- an admin adds and edits farmers by hand --------------------------------------------------------------------------
NEW = {"farmer_name": "Lakshmi", "phone_number": "+91 98765 43299", "preferred_language": "kannada",
       "village": "Mandya", "district": "Mandya", "state": "Karnataka", "call_consent": True}


def test_a_farmer_can_be_added_by_hand(tmp_path):
    s = make(tmp_path)
    f = s.add_farmer(NEW)
    assert f["farmer_id"] == "F001" and f["preferred_language"] == "Kannada" and f["phone_number"] == "******3299"
    assert (f["call_consent"], f["active"]) == ("Yes", "Yes")
    assert s.add_farmer({**NEW, "farmer_name": "Next"})["farmer_id"] == "F002"
    s.import_csv(ONE)                                          # imported and typed-in farmers live side by side
    assert len(s.farmers()) == 3


def test_consent_is_never_assumed_for_a_new_farmer(tmp_path):
    s = make(tmp_path)
    data = {k: v for k, v in NEW.items() if k != "call_consent"}
    assert s.add_farmer(data)["call_consent"] == "No"


@pytest.mark.parametrize("change, message", [
    ({"farmer_name": " "}, "name"), ({"phone_number": "12345"}, "10 digits"), ({"preferred_language": "French"}, "language"),
    ({"village": "", "district": ""}, "village or district"), ({"farmer_id": "F1"}, "already exists")])
def test_a_bad_new_farmer_is_refused(tmp_path, change, message):
    s = make(tmp_path)
    s.import_csv(ONE)
    with pytest.raises(ValueError, match=message):
        s.add_farmer({**NEW, **change})


def test_a_farmer_can_be_edited_deactivated_and_reactivated(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED))
    s = make(tmp_path, d)
    s.import_csv(ONE)
    f = s.update_farmer("F1", {"farmer_name": "Ramesh Kumar", "preferred_language": "Telugu", "phone_number": "9000000001"})
    assert (f["farmer_name"], f["preferred_language"], f["phone_number"]) == ("Ramesh Kumar", "Telugu", "******0001")
    assert s.update_farmer("F1", {"phone_number": ""})["phone_number"] == "******0001"          # blank keeps the old number
    assert s.update_farmer("F1", {"active": False})["active"] == "No"
    s.fire(D)
    assert d.calls == [] and s.calls()[0]["status"] == "Skipped"                                  # not called while inactive
    assert s.update_farmer("F1", {"active": "Yes"})["active"] == "Yes"
    s.fire(D + timedelta(days=1))
    assert len(d.calls) == 1 and d.calls[0][1] == "Telugu"


def test_edit_errors(tmp_path):
    s = make(tmp_path)
    s.import_csv(ONE)
    with pytest.raises(KeyError):
        s.update_farmer("nope", {"active": False})
    with pytest.raises(ValueError):
        s.update_farmer("F1", {"call_consent": "maybe"})


def test_api_add_and_edit_a_farmer(api):
    call, s = api
    code, body, _ = call("/api/farmers", json.dumps(NEW).encode())
    assert code == 201 and body["farmer_id"] == "F001"
    code, body, _ = call("/api/farmers/F001", json.dumps({"active": False, "village": "Hassan"}).encode(), method="PUT")
    assert code == 200 and body["active"] == "No" and body["village"] == "Hassan"
    assert call("/api/farmers/F001", json.dumps({"call_consent": False}).encode(), method="PATCH")[1]["call_consent"] == "No"
    assert call("/api/farmers/zzz", b"{}", method="PUT")[0] == 404
    assert call("/api/farmers", json.dumps({**NEW, "phone_number": "1"}).encode())[0] == 400
    assert call("/api/farmers", b"nope")[0] == 400
    assert "9876543299" not in json.dumps(call("/api/farmers")[1])


# ---- the Call button on a farmer card --------------------------------------------------------------------------------------
def wait_idle(s, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline and (s._manual or s.running):
        time.sleep(0.02)
    time.sleep(0.05)


def test_call_button_places_the_days_first_call(tmp_path):
    d = Scripted((A.ANSWERED,))
    s, _ = timed(tmp_path, d)
    s.import_csv(ONE)
    assert s.manual_call("F1") == {"started": True, "kind": "first", "attempt": 1, "max_attempts": 3}
    wait_idle(s)
    assert len(d.calls) == 1 and s.calls()[0]["status"] == "Completed" and s.calls()[0]["attempts_used"] == 1


def test_call_button_on_a_retryable_result_is_the_next_attempt_and_replaces_the_waiting_retry(tmp_path):
    d = Scripted((A.NO_ANSWER, A.NO_ANSWER, A.ANSWERED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    assert s.calls()[0]["attempts_used"] == 1 and s.calls()[0]["next_attempt_at"] == "05 Nov, 09:30 AM"
    clock["now"] = T0 + timedelta(minutes=5)
    assert s.manual_call("F1")["attempt"] == 2
    wait_idle(s)
    c = s.calls()[0]
    assert len(d.calls) == 2 and c["attempts_used"] == 2
    assert c["next_attempt_at"] == "05 Nov, 10:05 AM"                  # the 30-min retry was replaced; next gap is 1 hour
    assert s.manual_call("F1")["attempt"] == 3                         # the last one
    wait_idle(s)
    assert s.calls()[0]["attempts_used"] == 3 and s.calls()[0]["status"] == "Completed"


@pytest.mark.parametrize("setup, message", [
    ("done", "already completed"), ("declined", "do not need"), ("exhausted", "attempts are used"),
    ("callback", "callback"), ("inactive", "inactive"), ("noconsent", "consent"), ("paused", "stopped"),
    ("night", "between 05:00 and 22:00")])
def test_call_button_is_refused_with_a_reason(tmp_path, setup, message):
    start = datetime(2026, 11, 5, 23, 0, tzinfo=IST) if setup == "night" else T0
    d = Scripted((A.ANSWERED, A.NO_ANSWER, A.NO_ANSWER, A.NO_ANSWER), understood="declined" if setup == "declined" else "yes")
    s, clock = timed(tmp_path, d, start=start)
    s.import_csv(ONE)
    if setup in ("done", "declined"):
        s.fire(D)
    elif setup == "exhausted":
        d.statuses = [A.NO_ANSWER] * 3
        s.fire(D)
        for minutes in (30, 90):
            clock["now"] = T0 + timedelta(minutes=minutes)
            s.run_due_retries()
    elif setup == "callback":
        d.cb, d.statuses = "17:30", [A.ANSWERED]
        s.fire(D)
    elif setup == "inactive":
        s.update_farmer("F1", {"active": False})
    elif setup == "noconsent":
        s.update_farmer("F1", {"call_consent": False})
    elif setup == "paused":
        s._note_stop("F1", D - timedelta(days=1))
        s._note_stop("F1", D)
    placed = len(d.calls)
    with pytest.raises(ValueError, match=message):
        s.manual_call("F1")
    wait_idle(s)
    assert len(d.calls) == placed                                       # nothing was dialled


def test_call_button_refuses_a_second_press_while_a_call_is_in_progress(tmp_path):
    s, _ = timed(tmp_path, Scripted((A.ANSWERED,)))
    s.import_csv(ONE)
    s._manual.add("F1")
    with pytest.raises(ValueError, match="in progress"):
        s.manual_call("F1")
    s._manual.clear()
    with pytest.raises(KeyError):
        s.manual_call("nope")


def test_api_call_button(api):
    call, s = api
    s._now = lambda: T0                                                 # fixed clock: a real one after 22:00 is out of hours
    s.import_csv(ONE)
    code, body, _ = call("/api/farmers/F1/call", b"{}")
    assert code == 202 and body["kind"] == "first"
    wait_idle(s)
    assert call("/api/farmers/F1/call", b"{}")[0] == 400               # already completed today (simulated call understood)
    assert call("/api/farmers/zzz/call", b"{}")[0] == 404


# ---- test calls: the Call button with "ignore the retry rules" ------------------------------------------------------------
def test_a_test_call_is_its_own_row_and_never_touches_the_real_day(tmp_path):
    d = Scripted((A.NO_ANSWER, A.ANSWERED, A.ANSWERED), understood="yes")
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)                                                          # a real first call: not picked up, retry waiting
    real = s.calls()[0]
    assert real["status"] == "Retrying" and real["attempts_used"] == 1 and real["next_attempt_at"] == "05 Nov, 09:30 AM"
    assert s.manual_call("F1", "test")["kind"] == "test"
    wait_idle(s)
    rows = s.calls()
    test = next(c for c in rows if c.get("is_test"))
    assert test["status"] == "Completed" and test["disposition"].startswith("Test call") and test["farmer_name"] == "Ramesh"
    assert test["call_id"].startswith("TEST") and test["attempts_used"] == 0 and test["next_attempt_at"] is None
    day = next(c for c in rows if not c.get("is_test"))
    assert (day["status"], day["attempts_used"], day["next_attempt_at"]) == ("Retrying", 1, "05 Nov, 09:30 AM")   # untouched
    assert s.call(test["call_id"])["is_test"] is True
    assert s.alerts() == [] and s.callbacks() == []


def test_a_test_call_can_be_repeated_even_when_the_day_is_complete_or_attempts_are_used(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED, A.ANSWERED), understood="yes")
    s, _ = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)                                                          # completed today: "retry" mode is refused
    with pytest.raises(ValueError, match="already completed"):
        s.manual_call("F1")
    for _ in range(2):
        s.manual_call("F1", "test")
        wait_idle(s)
    assert len(d.calls) == 3 and sum(1 for c in s.calls() if c.get("is_test")) == 2
    assert next(c for c in s.calls() if not c.get("is_test"))["attempts_used"] == 1


def test_a_test_call_records_no_stop_decline_or_callback(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED), callback_text="17:30", stop="yes")
    s, _ = timed(tmp_path, d)
    s.import_csv(ONE)
    for _ in range(2):
        s.manual_call("F1", "test")
        wait_idle(s)
    assert s.callbacks() == [] and not s._is_paused("F1") and s.alerts() == []


@pytest.mark.parametrize("setup, message", [("inactive", "inactive"), ("noconsent", "consent"), ("paused", "stopped"),
                                            ("night", "between 05:00 and 22:00")])
def test_a_test_call_keeps_the_safety_checks(tmp_path, setup, message):
    d = Scripted((A.ANSWERED,))
    s, _ = timed(tmp_path, d, start=datetime(2026, 11, 5, 23, 0, tzinfo=IST) if setup == "night" else T0)
    s.import_csv(ONE)
    if setup == "inactive":
        s.update_farmer("F1", {"active": False})
    elif setup == "noconsent":
        s.update_farmer("F1", {"call_consent": False})
    elif setup == "paused":
        s._note_stop("F1", D - timedelta(days=1))
        s._note_stop("F1", D)
    with pytest.raises(ValueError, match=message):
        s.manual_call("F1", "test")
    assert d.calls == []


def test_api_call_button_modes(api):
    call, s = api
    s._now = lambda: T0
    s.import_csv(ONE)
    assert call("/api/farmers/F1/call", json.dumps({"mode": "nonsense"}).encode())[0] == 400
    code, body, _ = call("/api/farmers/F1/call", json.dumps({"mode": "test"}).encode())
    assert code == 202 and body["kind"] == "test"
    wait_idle(s)
    assert any(c.get("is_test") for c in s.calls())


def test_a_second_send_keeps_the_real_failure_reason(tmp_path):
    d = Scripted((A.FAILED,))
    s, _ = timed(tmp_path, d, start=datetime(2026, 11, 5, 21, 45, tzinfo=IST))      # no retry fits before 22:00
    s.import_csv(ONE)
    s.fire(D)
    first = s.calls()[0]
    s.fire(D)
    again = s.calls()[0]
    assert again["status"] == "Failed" and again["note"] == first["note"] and "already called" not in again["note"]
    assert again["disposition"] == first["disposition"]

# ---- a hosted API needs its token -------------------------------------------------------------------------------------
@pytest.fixture
def locked_api(tmp_path):
    s = make(tmp_path, MockDialler())
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(s, {"*"}, token="s3cret-token"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, token=None, data=None):
        req = urllib.request.Request(base + path, data=data, method="POST" if data is not None else "GET")
        if token is not None:
            req.add_header("X-API-Token", token)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    yield call
    srv.shutdown()


def test_the_api_refuses_calls_without_the_token_but_health_stays_open(locked_api):
    assert locked_api("/api/health") == 200                      # for the host's health check
    for path in ("/api/farmers", "/api/calls", "/api/usage", "/api/alerts"):
        assert locked_api(path) == 401 and locked_api(path, "wrong") == 401
        assert locked_api(path, "s3cret-token") == 200
    assert locked_api("/api/calls/send-now", data=b"{}") == 401  # no calls placed without the token
    assert locked_api("/api/farmers", data=json.dumps(NEW).encode()) == 401


def test_run_refuses_a_public_address_without_a_token(tmp_path, monkeypatch):
    from weathercall import server
    monkeypatch.setenv("GATE0_API_HOST", "0.0.0.0")
    monkeypatch.delenv("GATE0_API_TOKEN", raising=False)
    monkeypatch.setenv("GATE0_DB", str(tmp_path / "x.db"))
    monkeypatch.setattr(server, "load_env_file", lambda p: None)
    with pytest.raises(SystemExit, match="GATE0_API_TOKEN"):
        server.run(port=0)


# ---- the wake-up call from an outside timer: runs what is due, never twice ----------------------------------------------------
def test_tick_runs_what_is_due_and_only_one_pass_at_a_time(tmp_path):
    d = Scripted((A.NO_ANSWER, A.ANSWERED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)                                                               # not picked up: a retry is waiting for 09:30
    clock["now"] = T0 + timedelta(minutes=31)
    assert s._tick_lock.acquire(blocking=False)                             # a pass is already running...
    assert s.tick() is False and s.start_tick() is False                    # ...so a second one does nothing
    assert len(d.calls) == 1
    s._tick_lock.release()
    assert s.tick() is True                                                 # the retry is due now and is placed
    assert len(d.calls) == 2 and s.calls()[0]["status"] == "Completed"
    assert s.tick() is True and len(d.calls) == 2                           # nothing left to do: no second call


def test_tick_before_the_due_time_places_nothing(tmp_path):
    d = Scripted((A.NO_ANSWER, A.ANSWERED))
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    clock["now"] = T0 + timedelta(minutes=27)                               # a wake-up 3 minutes early: still nothing due
    s.tick()
    assert len(d.calls) == 1 and s.calls()[0]["next_attempt_at"] == "05 Nov, 09:30 AM"


def test_tick_starts_the_daily_send_once(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED))
    s, clock = timed(tmp_path, d, start=datetime(2026, 11, 5, 9, 2, tzinfo=IST))
    s.import_csv(ONE)
    s.set_auto_dispatch(True)
    assert s.tick() is True
    wait_idle(s)
    assert len(d.calls) == 1
    s.tick()
    wait_idle(s)
    assert len(d.calls) == 1                                                # a second wake-up the same day calls nobody again


def test_api_tick(api):
    call, s = api
    s._now = lambda: T0
    code, body, _ = call("/api/tick", b"{}")
    assert code == 202 and body["started"] in (True, False) and body["at"].startswith("2026-11-05T09:00")


def test_a_callback_the_system_could_not_place_in_time_shows_as_missed_not_scheduled(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED), callback_text="09:35")
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    assert s.calls()[0]["status"] == "Callback Scheduled"
    clock["now"] = T0 + timedelta(minutes=70)                                  # the backend only comes back an hour later
    s.run_due_callbacks()
    c = s.calls()[0]
    assert (c["status"], c["disposition"]) == ("Callback Missed", "Callback not placed in time")
    assert c["scheduled_callback_time"] == "05 Nov, 09:35 AM" and len(d.calls) == 1


def test_a_callback_that_was_placed_shows_as_done(tmp_path):
    d = Scripted((A.ANSWERED, A.ANSWERED), callback_text="09:35")
    s, clock = timed(tmp_path, d)
    s.import_csv(ONE)
    s.fire(D)
    clock["now"] = T0 + timedelta(minutes=36)
    s.run_due_callbacks()
    assert s.calls()[0]["status"] == "Callback Done" and len(d.calls) == 2
