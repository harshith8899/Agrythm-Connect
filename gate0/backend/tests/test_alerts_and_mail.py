"""Notes for the team that can be dismissed, errors that say which error, and mail through an HTTPS API."""
import io
import json
import smtplib
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

import pytest

from weathercall.adapters.dialers import SarvamDialler, SarvamHTTPError
from weathercall.adapters.mailer import MailHTTPError, NullMailer, ResendMailer, SmtpMailer, make_mailer
from weathercall.adapters.dialers import MockDialler
from weathercall.messages import KIND_WEATHER, build_email
from weathercall.server import make_handler
from weathercall.service import DashboardService, IST, _error_detail

T0 = datetime(2026, 11, 16, 20, 0, tzinfo=IST)


# ---- errors say which error, never the message ---------------------------------------------------------------------
def test_error_detail_names_the_type_and_a_code_but_never_the_message():
    assert _error_detail(OSError(101, "Network is unreachable +919876543210")) == "OSError (errno 101)"
    assert _error_detail(smtplib.SMTPAuthenticationError(535, b"bad credentials for a@b.c")) == "SMTPAuthenticationError (SMTP 535)"
    assert _error_detail(SarvamHTTPError("HTTP 422 invalid_parameter")) == "HTTP 422 invalid_parameter"
    assert _error_detail(ValueError("a@b.c")) == "ValueError"
    assert _error_detail(ConnectionError("simulated")) == "ConnectionError"


# ---- the Resend mailer ------------------------------------------------------------------------------------------
class Opener:
    def __init__(self, error=None):
        self.error, self.requests = error, []

    def __call__(self, req, timeout=0):
        self.requests.append((req.full_url, req.get_method(), dict(req.header_items()), json.loads(req.data)))
        if self.error:
            raise self.error
        return io.BytesIO(b'{"id": "x"}')


def test_resend_sends_json_over_https_with_the_logo_as_a_web_address():
    op = Opener()
    m = ResendMailer("re_secret_key", "Agrythm <hello@example.org>", team="team@example.org",
                     logo_url="https://example.org/logo.png", opener=op)
    subject, text, html = build_email("Ramesh", "Mandya", {"temp_min": 14, "temp_max": 27, "wind": 12, "rain": 40, "humidity": 70}, KIND_WEATHER)
    m.send("to@example.org", subject, text, html)
    url, method, headers, body = op.requests[0]
    assert url == "https://api.resend.com/emails" and method == "POST" and headers["Authorization"] == "Bearer re_secret_key"
    assert headers["User-agent"].startswith("agrythm")
    assert body["from"] == "Agrythm <hello@example.org>" and body["to"] == ["to@example.org"] and body["bcc"] == ["team@example.org"]
    assert body["subject"] == subject and body["text"] == text
    assert 'src="https://example.org/logo.png"' in body["html"] and "cid:" not in body["html"]
    assert "re_secret_key" not in repr(m)


def test_resend_without_a_logo_address_leaves_the_picture_out_and_defaults_the_sender():
    op = Opener()
    m = ResendMailer("k", opener=op)
    html = build_email("Ramesh", "Mandya", {"temp_min": 1, "temp_max": 2, "wind": 3, "rain": 4, "humidity": 5}, KIND_WEATHER)[2]
    m.send("to@example.org", "s", "t", html)
    body = op.requests[0][3]
    assert "<img" not in body["html"] and body["from"].endswith("<onboarding@resend.dev>") and "bcc" not in body


def test_a_resend_error_is_reported_by_code_and_name_never_the_message():
    err = urllib.error.HTTPError("u", 403, "x", {}, io.BytesIO(json.dumps({"name": "validation_error", "message": "to a@b.c is not allowed"}).encode()))
    with pytest.raises(MailHTTPError) as e:
        ResendMailer("k", opener=Opener(err)).send("a@b.c", "s", "t")
    assert e.value.safe_text == "HTTP 403 validation_error" and "a@b.c" not in str(e.value)


def test_the_mailer_is_chosen_by_the_environment_and_resend_wins_over_smtp():
    assert isinstance(make_mailer({}), NullMailer)
    smtp = {"GATE0_SMTP_HOST": "smtp.example.com", "GATE0_SMTP_USER": "u", "GATE0_SMTP_PASSWORD": "p"}
    assert isinstance(make_mailer(smtp), SmtpMailer)
    both = make_mailer({**smtp, "GATE0_RESEND_API_KEY": "re_x", "GATE0_MAIL_LOGO_URL": "https://example.org/l.png"})
    assert isinstance(both, ResendMailer) and both.logo_url == "https://example.org/l.png"


# ---- a Sarvam error says which one ---------------------------------------------------------------------------------
ENV = {"SARVAM_ORG_ID": "o", "SARVAM_WORKSPACE_ID": "w", "SARVAM_APP_ID": "a", "SARVAM_CONNECTION_ID": "c",
       "SARVAM_AGENT_PHONE": "+910000000000", "SARVAM_AGENT_API_KEY": "k", "SARVAM_INBOUND_DEPLOYMENT_ID": "dep-1"}


def test_a_failed_cohort_push_says_the_http_code_and_sarvams_error_code_but_not_its_message():
    err = urllib.error.HTTPError("u", 422, "x", {}, io.BytesIO(json.dumps(
        {"error": {"code": "invalid_parameter", "message": "user +919876543210 is not valid"}}).encode()))
    d = SarvamDialler(env=ENV, opener=Opener(err))
    with pytest.raises(SarvamHTTPError) as e:
        d.push_inbound_many([{"fid": "F1", "phone": "9876543210", "language_name": "Hindi", "variables": {}}], "roster-x")
    assert e.value.safe_text.startswith("HTTP 422 invalid_parameter: ") and "9876" not in str(e.value)
    assert "is not valid" in e.value.safe_text                              # the part that says what was wrong is kept


# ---- notes for the team --------------------------------------------------------------------------------------------
def service(tmp_path, now=T0):
    return DashboardService(str(tmp_path / "a.db"), dialler=MockDialler(), env={"GATE0_WEATHER": "mock"}, now=lambda: now)


def test_notes_have_ids_and_can_be_dismissed_one_by_one_or_all_at_once(tmp_path):
    s = service(tmp_path)
    for i in range(3):
        s._alert("k", "", f"note {i}")
    notes = s.alerts()
    assert [n["text"] for n in notes] == ["note 2", "note 1", "note 0"] and all(isinstance(n["id"], int) for n in notes)
    assert s.dismiss_alerts([notes[1]["id"]]) == 1
    assert [n["text"] for n in s.alerts()] == ["note 2", "note 0"]
    assert s.dismiss_alerts([999, "x"]) == 0                                 # an unknown id removes nothing
    assert s.dismiss_alerts(None) == 2 and s.alerts() == []


def test_the_same_note_is_not_repeated_within_30_minutes(tmp_path):
    clock = [T0]
    s = DashboardService(str(tmp_path / "a.db"), dialler=MockDialler(), env={"GATE0_WEATHER": "mock"}, now=lambda: clock[0])
    s._alert("inbound_push_failed", "", "could not be updated (HTTP 422)")
    s._alert("inbound_push_failed", "", "could not be updated (HTTP 422)")
    s._alert("inbound_push_failed", "", "could not be updated (HTTP 500)")        # a different note is kept
    assert len(s.alerts()) == 2
    clock[0] = T0 + timedelta(minutes=31)
    s._alert("inbound_push_failed", "", "could not be updated (HTTP 422)")
    assert len(s.alerts()) == 3


def test_notes_are_dismissed_through_the_api(tmp_path):
    s = service(tmp_path)
    for i in range(3):
        s._alert("k", "", f"note {i}")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(s, {"*"}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"

    def post(body):
        req = urllib.request.Request(base + "/api/alerts/dismiss", method="POST", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req).read())

    try:
        first = json.loads(urllib.request.urlopen(base + "/api/alerts").read())[0]["id"]
        assert post({"id": first}) == {"removed": 1}
        assert post({"ids": [first]}) == {"removed": 0}
        assert post({"all": True}) == {"removed": 2}
        assert json.loads(urllib.request.urlopen(base + "/api/alerts").read()) == []
    finally:
        srv.shutdown()


# ---- the mail setup check and the test email -----------------------------------------------------------------------
def test_the_mail_status_never_shows_a_key_or_a_full_address(tmp_path):
    from weathercall.adapters.mailer import RecordingMailer
    s = DashboardService(str(tmp_path / "m.db"), dialler=MockDialler(), mailer=ResendMailer("re_secret"),
                         env={"GATE0_WEATHER": "mock", "GATE0_MAIL_TEST_TO": "Tester@Example.com"}, now=lambda: T0)
    m = s.mail_status()
    assert m == {"provider": "Resend", "live": True, "test_to": "t***@example.com", "test_mode": True}
    assert "re_secret" not in str(m) and "tester@example.com" not in str(m)


def test_the_test_email_goes_to_the_test_address_and_is_recorded(tmp_path):
    from weathercall.adapters.mailer import RecordingMailer
    mail = RecordingMailer()
    s = DashboardService(str(tmp_path / "m.db"), dialler=MockDialler(), mailer=mail,
                         env={"GATE0_WEATHER": "mock", "GATE0_MAIL_TEST_TO": "tester@example.com"}, now=lambda: T0)
    assert s.send_test_email() == {"status": "sent", "note": ""}
    assert mail.sent[0][0] == "tester@example.com" and mail.sent[0][1].startswith("[Setup test] Weather update")
    row = s.messages()[0]
    assert row["farmer_id"] == "(setup test)" and row["status"] == "sent" and row["kind"].startswith("test:setup:")


def test_the_test_email_says_why_it_could_not_be_sent(tmp_path):
    from weathercall.adapters.mailer import RecordingMailer
    env = {"GATE0_WEATHER": "mock", "GATE0_MAIL_TEST_TO": "tester@example.com"}
    s = DashboardService(str(tmp_path / "a.db"), dialler=MockDialler(), mailer=NullMailer(), env=env, now=lambda: T0)
    r = s.send_test_email()
    assert r["status"] == "skipped" and "GATE0_RESEND_API_KEY" in r["note"]
    (tmp_path / "b").mkdir()
    s2 = DashboardService(str(tmp_path / "b" / "b.db"), dialler=MockDialler(), mailer=RecordingMailer(fail=True), env=env, now=lambda: T0)
    assert s2.send_test_email() == {"status": "failed", "note": "ConnectionError"}
    (tmp_path / "c").mkdir()
    s3 = DashboardService(str(tmp_path / "c" / "c.db"), dialler=MockDialler(), mailer=NullMailer(), env={"GATE0_WEATHER": "mock"}, now=lambda: T0)
    assert s3.send_test_email()["status"] == "skipped" and "GATE0_MAIL_TEST_TO" in s3.send_test_email()["note"]


def test_quoted_values_in_a_sarvam_message_are_masked():
    from weathercall.adapters.dialers import _strip_quoted
    assert _strip_quoted("value 'Ramesh Kumar' is not allowed for \"farmer_name\"") == "value '...' is not allowed for '...'"
