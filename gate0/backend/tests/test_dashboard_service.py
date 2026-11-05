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
    ((A.NO_ANSWER,), "yes", ("Unanswered", "No Answer")), ((A.BUSY,), "yes", ("Unanswered", "Busy")),
    ((A.FAILED,), "yes", ("Failed", "Provider Error")), ((A.ANSWERED,), "unclear", ("Not Confirmed", "Heard, not confirmed")),
    ((A.ANSWERED,), "yes", ("Completed", "Weather Delivered"))])
def test_dashboard_status_for_each_outcome(tmp_path, statuses, understood, expected):
    s = make(tmp_path, Scripted(statuses, understood=understood))
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
    s = make(tmp_path, Boom())
    s.import_csv(ONE)
    s.fire(D)
    c = s.calls()[0]
    assert c["status"] == "Failed" and c["note"] == "ConnectionError" and "9876543210" not in json.dumps(c)


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

    def call(path, data=None, origin=None):
        req = urllib.request.Request(base + path, data=data, method="POST" if data is not None else "GET")
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
