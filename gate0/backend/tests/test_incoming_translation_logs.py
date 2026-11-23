"""Incoming calls on the dashboard, English for what was said, and removing email log rows."""
import io
import json
import urllib.error

import pytest

from test_callback_in import A, D, Dial, T0, make, rings
from weathercall.adapters.mailer import RecordingMailer
from weathercall.adapters.translate import SarvamTranslator, TranslateError, make_translator
from weathercall.contracts import ProviderCallResult
from weathercall.messages import KIND_WEATHER
from weathercall.service import DashboardService, IST
from datetime import timedelta


# ---- incoming calls ---------------------------------------------------------------------------------------------
def test_a_call_from_an_unknown_number_is_listed_as_incoming(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    rings(d, last4="9999", attempt_id="IN9", duration=12)
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 0                   # not a result for anyone
    row = next(c for c in s.calls() if c["call_id"] == "IN-IN9")
    assert row["direction"] == "incoming" and row["farmer_name"] == "Unknown number" and row["phone_number"] == "******9999"
    assert row["duration_seconds"] == 12 and "unknown number" in row["disposition"].lower() and row["status"] == "Skipped"
    assert s.sync_inbound(T0 + timedelta(minutes=20)) == 0
    assert len([c for c in s.calls() if c["call_id"] == "IN-IN9"]) == 1       # logged once


def test_a_call_from_an_inactive_farmer_is_listed_with_their_name_and_gets_no_result(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)                                                  # F3 has not given consent
    rings(d, last4="3212", attempt_id="IN3")
    s.sync_inbound(T0 + timedelta(minutes=15))
    row = next(c for c in s.calls() if c["call_id"] == "IN-IN3")
    assert row["farmer_name"] == "Gopal" and row["direction"] == "incoming" and "not a registered farmer" in row["disposition"].lower()
    assert not any(c["farmer_id"] == "F3" and c["call_id"] != "IN-IN3" for c in s.calls())     # no result was made for them


def test_a_registered_farmers_call_to_us_shows_in_their_row_as_incoming_and_outgoing_ones_do_not(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    s.fire_one("F1", D)                                                       # our own call, not picked up
    s._live_clear("F1")
    assert next(c for c in s.calls() if c["farmer_id"] == "F1")["direction"] == "outgoing"
    rings(d)
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    row = next(c for c in s.calls() if c["farmer_id"] == "F1" and not c["call_id"].startswith("IN-"))
    assert row["direction"] == "incoming" and row["status"] == "Completed"


# ---- removing email log rows --------------------------------------------------------------------------------------
def _mail_service(tmp_path):
    mail = RecordingMailer()
    s = DashboardService(str(tmp_path / "m.db"), dialler=Dial(ready=False), env={"GATE0_WEATHER": "mock", "GATE0_MAIL_TEST_TO": "t@x.org"},
                         now=lambda: T0, mailer=mail)
    s.async_inbound = False
    s.import_csv("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent\n"
                 "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes\nF2,Lakshmi,9876543211,Mysuru,Mysuru,Karnataka,English,Yes\n")
    return s, mail


def test_email_log_rows_can_be_removed_one_by_one_or_all_and_the_email_is_still_not_sent_twice(tmp_path):
    s, mail = _mail_service(tmp_path)
    w = {"temp_min": 1, "temp_max": 2, "wind": 3, "rain": 4, "humidity": 5}
    s._send_message("F1", D, KIND_WEATHER, w)
    s._send_message("F2", D, KIND_WEATHER, w)
    rows = s.messages()
    assert len(rows) == 2 and all(r["key"].count("|") == 2 for r in rows)
    assert s.dismiss_messages([rows[0]["key"]]) == 1 and len(s.messages()) == 1
    assert s.dismiss_messages(["nonsense", "a|b|c"]) == 0
    assert s.dismiss_messages(None) == 1 and s.messages() == []
    assert s._send_message("F1", D, KIND_WEATHER, w) == "not sent: already sent"        # hidden, not forgotten
    assert len(mail.sent) == 2


def test_email_log_rows_are_removed_through_the_api(tmp_path):
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from weathercall.server import make_handler
    s, _ = _mail_service(tmp_path)
    w = {"temp_min": 1, "temp_max": 2, "wind": 3, "rain": 4, "humidity": 5}
    s._send_message("F1", D, KIND_WEATHER, w)
    s._send_message("F2", D, KIND_WEATHER, w)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(s, {"*"}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"

    def post(body):
        req = urllib.request.Request(base + "/api/messages/dismiss", method="POST", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req).read())

    try:
        key = json.loads(urllib.request.urlopen(base + "/api/messages").read())[0]["key"]
        assert post({"key": key}) == {"removed": 1}
        assert post({"all": True}) == {"removed": 1}
        assert json.loads(urllib.request.urlopen(base + "/api/messages").read()) == []
    finally:
        srv.shutdown()


# ---- English for what was said ----------------------------------------------------------------------------------------
class FakeTranslator:
    def __init__(self, fail_after=None):
        self.calls, self.fail_after = [], fail_after

    def needs_translation(self, language):
        return SarvamTranslator.needs_translation(language)

    def translate(self, text, language):
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise TranslateError("HTTP 429 rate_limit")
        self.calls.append(text)
        return f"EN({text})"


def _with_transcript(tmp_path, language="hi", translator="fake"):
    tr = FakeTranslator() if translator == "fake" else translator
    s = DashboardService(str(tmp_path / "t.db"), dialler=Dial(ready=False), env={"GATE0_WEATHER": "mock"}, now=lambda: T0, translator=tr)
    s.import_csv("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent\n"
                 "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes\n")
    s._save("F1", D, status="answered", language=language, transcript=json.dumps(
        [{"speaker": "Agent", "text": "नमस्ते रमेश जी"}, {"speaker": "Farmer", "text": "हाँ"}]))
    return s, tr, s.calls()[0]["call_id"]


def test_the_transcript_comes_back_with_english_under_each_turn_and_each_turn_is_translated_once(tmp_path):
    s, tr, cid = _with_transcript(tmp_path)
    r = s.transcript_english(cid)
    assert r["available"] and r["error"] == "" and [t["english"] for t in r["turns"]] == ["EN(नमस्ते रमेश जी)", "EN(हाँ)"]
    assert r["turns"][0]["speaker"] == "Agent"
    s.transcript_english(cid)
    assert len(tr.calls) == 2                                                  # the second time came from what was kept


def test_an_english_call_needs_no_translation_and_no_key_says_so(tmp_path):
    s, tr, cid = _with_transcript(tmp_path, language="en")
    assert [t["english"] for t in s.transcript_english(cid)["turns"]] == ["नमस्ते रमेश जी", "हाँ"] and tr.calls == []
    (tmp_path / "n").mkdir()
    s2, _, cid2 = _with_transcript(tmp_path / "n", translator=None)
    s2.translator = None
    r = s2.transcript_english(cid2)
    assert r["available"] is False and "SARVAM_API_KEY" in r["error"] and r["turns"][0]["text"]


def test_a_translation_failure_keeps_what_was_done_and_says_which_error(tmp_path):
    (tmp_path / "f").mkdir()
    s, tr, cid = _with_transcript(tmp_path / "f", translator=FakeTranslator(fail_after=1))
    r = s.transcript_english(cid)
    assert r["turns"][0]["english"] == "EN(नमस्ते रमेश जी)" and r["turns"][1]["english"] == ""
    assert r["error"] == "Translation failed (HTTP 429 rate_limit)"


def test_the_sarvam_translator_sends_the_text_and_language_and_reports_errors_by_code(tmp_path):
    seen = []

    def ok(req, timeout=0):
        seen.append((req.full_url, dict(req.header_items()), json.loads(req.data)))
        return io.BytesIO(json.dumps({"translated_text": "Hello Ramesh"}).encode())

    t = SarvamTranslator("sk_secret", opener=ok)
    assert t.translate("नमस्ते रमेश", "hi") == "Hello Ramesh"
    url, headers, body = seen[0]
    assert url == "https://api.sarvam.ai/translate" and headers["Api-subscription-key"] == "sk_secret"
    assert body == {"input": "नमस्ते रमेश", "source_language_code": "hi-IN", "target_language_code": "en-IN"}
    assert "sk_secret" not in repr(t) and t.translate("hello", "en") == "hello" and len(seen) == 1

    def bad(req, timeout=0):
        raise urllib.error.HTTPError("u", 403, "x", {}, io.BytesIO(json.dumps({"error": {"code": "forbidden", "message": "key sk_x for text"}}).encode()))

    with pytest.raises(TranslateError) as e:
        SarvamTranslator("k", opener=bad).translate("नमस्ते", "hi")
    assert e.value.safe_text == "HTTP 403 forbidden"


def test_the_translator_key_comes_from_the_environment():
    assert make_translator({}) is None
    assert isinstance(make_translator({"SARVAM_API_KEY": "k"}), SarvamTranslator)
    assert isinstance(make_translator({"SARVAM_TRANSLATE_API_KEY": "k"}), SarvamTranslator)


# ---- the real shape of Sarvam's records for calls to the line ------------------------------------------------------------
def test_two_calls_to_the_line_are_both_logged_and_two_numbers_ending_the_same_are_told_apart(tmp_path):
    import hashlib
    from weathercall.adapters.dialers import SarvamDialler
    from weathercall.adapters.sarvam_agent import to_e164

    def record(number, interaction, minute):
        return {"attempt_id": "NO_JOB_ID", "interaction_id": interaction, "channel_direction": "inbound",
                "connectivity_status": "connected", "duration_in_seconds": 13, "attempted_at": f"2026-11-17T05:{minute}:20",
                "user_contact_masked": "+91******" + number[-4:],
                "user_contact_hashed": hashlib.sha256(to_e164(number).encode()).hexdigest()}

    env = {"SARVAM_ORG_ID": "o", "SARVAM_WORKSPACE_ID": "w", "SARVAM_APP_ID": "a", "SARVAM_CONNECTION_ID": "c",
           "SARVAM_AGENT_PHONE": "+910000000000", "SARVAM_AGENT_API_KEY": "k", "SARVAM_INBOUND_DEPLOYMENT_ID": "dep"}
    items = [record("9000003736", "20261117/aaa-10:36:20", "06"), record("9111113736", "20261117/bbb-10:40:11", "10")]

    class Opener:
        def __call__(self, req, timeout=0):
            return io.BytesIO(json.dumps({"items": items}).encode())

    dialler = SarvamDialler(env=env, opener=Opener())
    s = DashboardService(str(tmp_path / "h.db"), dialler=dialler, env={"GATE0_WEATHER": "mock"}, now=lambda: T0 + timedelta(hours=8))
    s.async_inbound = False
    s.import_csv("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
                 "F1,Ramesh,9000003736,Mandya,Mandya,Karnataka,Hindi,Yes,No\n"          # inactive
                 "F2,Lakshmi,9222223736,Mysuru,Mysuru,Karnataka,English,Yes,Yes\n")     # same last 4 digits, different number
    s.sync_inbound(T0 + timedelta(hours=8))
    rows = {c["call_id"]: c for c in s.calls() if c["call_id"].startswith("IN-")}
    assert set(rows) == {"IN-20261117/aaa-10:36:20", "IN-20261117/bbb-10:40:11"}      # each call has its own row
    first, second = rows["IN-20261117/aaa-10:36:20"], rows["IN-20261117/bbb-10:40:11"]
    assert first["farmer_name"] == "Ramesh" and "not a registered farmer" in first["disposition"].lower()   # the exact number, not the last 4
    assert second["farmer_name"] == "Unknown number"                          # 9111113736 is nobody's, though it ends like two others
    assert s.incoming()["sync"]["seen"] == 2 and s.incoming()["sync"]["error"] == ""


# ---- a successful incoming call: the weather email goes out, and a second call the same day is not served ------------------
def test_a_successful_incoming_call_sends_the_weather_email_even_before_the_daily_call(tmp_path):
    d = Dial()
    s, mail = make(tmp_path, d)                                                # F1 has not been called today: no weather saved yet
    rings(d)
    assert s.sync_inbound(T0 + timedelta(minutes=15)) == 1
    assert any("Weather update for Mandya" in m[1] for m in mail.sent)         # the farmer understood: the email follows
    saved = s._saved_weather("F1", D.isoformat())
    assert saved["temp_max"] is not None and saved["source"]                   # the weather the farmer was told is kept with the result


def test_after_a_successful_call_the_line_is_told_not_to_give_the_weather_again_today(tmp_path):
    d = Dial()
    s, _ = make(tmp_path, d)
    rings(d)
    s.sync_inbound(T0 + timedelta(minutes=15))
    e = d.pushed("F1")
    assert e["state"] == "completed" and "do not give the weather again" in e["variables"]["callback_context"]
    rings(d, attempt_id="IN2", minutes=40)                                     # a second call the same day
    s.sync_inbound(T0 + timedelta(minutes=50))
    assert len([m for m in s.messages() if m["kind"] == "weather"]) == 1       # still one email for the day
    assert next(c for c in s.calls() if c["call_id"].startswith("F1-"))["status"] == "Completed"        # the second call is listed on its own row


def test_a_call_from_a_farmer_whose_day_is_already_completed_is_still_listed_as_an_incoming_call(tmp_path):
    d = Dial(status=A.ANSWERED, understood="yes")
    s, _ = make(tmp_path, d)
    s.fire(D)                                                                  # F1 is called and understood: the day is completed
    s._refresh_inbound(force=True)
    rings(d, attempt_id="IN-LATE", minutes=40)
    s.sync_inbound(T0 + timedelta(minutes=50))
    rows = [c for c in s.calls() if c["call_id"] == "IN-IN-LATE"]
    assert len(rows) == 1                                                       # visible in the call log
    row = rows[0]
    assert row["direction"] == "incoming" and row["farmer_id"] == "F1" and row["farmer_name"] != "Unknown number"
    assert row["disposition"] == "Incoming call: weather already given today"
    assert next(c for c in s.calls() if c["call_id"] == f"F1-{D.isoformat()}")["status"] == "Completed"   # the day's result is untouched
