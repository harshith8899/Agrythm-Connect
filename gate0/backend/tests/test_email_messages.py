"""The written message (email) after a call: when it is sent, what it says, and that it never goes twice."""
from datetime import date, datetime

from weathercall.adapters.mailer import NullMailer, RecordingMailer, SmtpMailer, make_mailer
from weathercall.contracts import AttemptStatus, Language, ProviderCallResult
from weathercall.messages import (KIND_CALLBACK_MISSED, KIND_CALLBACK_WEATHER, KIND_MISSED, KIND_WEATHER, KINDS,
                                  build_email)
from weathercall.service import DashboardService, IST, mask_email

A = AttemptStatus
CSV = ("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active,Email\n"
       "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes,Yes,Ramesh@Example.com\n"
       "F2,Lakshmi,9876543211,Mysuru,Mysuru,Karnataka,English,Yes,Yes,\n")
D = date(2026, 11, 15)
T0 = datetime(2026, 11, 15, 9, 0, tzinfo=IST)
WEATHER = {"temp_min": 14.0, "temp_max": 27.5, "wind": 12, "rain": 40, "humidity": 70, "source": "mock"}


class Dial:
    mode, live = "t", False

    def __init__(self, status=A.ANSWERED, understood="yes", callback="", error=""):
        self.status, self.understood, self.callback, self.error = status, understood, callback, error

    def place(self, phone, language_name, variables):
        return ProviderCallResult(self.status, provider_call_id="X1", duration_s=30, error=self.error)

    def outputs(self, attempt_id):
        return {"understood_weather": self.understood, "stop_calls_requested": "no", "call_summary": "s",
                "callback_time": self.callback}


def make(tmp_path, dialler, mailer=None, now=T0):
    mail = mailer or RecordingMailer()
    s = DashboardService(str(tmp_path / "m.db"), dialler=dialler, env={"GATE0_WEATHER": "mock"}, now=lambda: now, mailer=mail)
    s.import_csv(CSV)
    s.ports = s._make_ports()
    return s, mail


def test_the_sheet_email_is_kept_lowercased_and_never_shown_in_full(tmp_path):
    s, _ = make(tmp_path, Dial())
    f1, f2 = s.farmers()
    assert f1["email"] == "r***@example.com" and "ramesh@example.com" not in str(s.farmers())
    assert f2["email"] == ""
    assert mask_email("not an email") == ""


def test_a_farmer_can_be_added_with_an_email_and_a_bad_one_is_refused(tmp_path):
    s, _ = make(tmp_path, Dial())
    base = {"farmer_name": "Anil", "phone_number": "9876500000", "village": "Mandya", "preferred_language": "Hindi"}
    assert s.add_farmer({**base, "email": "anil@x.org"})["email"] == "a***@x.org"
    try:
        s.add_farmer({**base, "email": "nope"})
        assert False
    except ValueError as e:
        assert "email" in str(e)
    s.update_farmer("F1", {"email": ""})                       # blank keeps the saved address
    assert next(f for f in s.farmers() if f["farmer_id"] == "F1")["email"] == "r***@example.com"


def test_a_successful_call_sends_the_weather_email_once(tmp_path):
    s, mail = make(tmp_path, Dial())
    s.fire_one("F1", D)
    assert len(mail.sent) == 1
    to, subject, body = mail.sent[0]
    saved = s._saved_weather("F1", D.isoformat())
    assert to == "ramesh@example.com" and "Mandya" in subject and "Ramesh" in body
    assert all(str(int(saved[k])) in body for k in ("temp_min", "temp_max", "wind", "rain", "humidity"))
    assert "could not reach you" not in body                  # that line is only for a missed call
    assert s._send_message("F1", D, KIND_WEATHER) == "not sent: already sent"      # never twice for the same day
    assert [m["status"] for m in s.messages()] == ["sent"]


def test_the_last_failed_attempt_sends_a_we_tried_to_reach_you_email(tmp_path):
    s, mail = make(tmp_path, Dial(A.NO_ANSWER, ""), now=datetime(2026, 11, 15, 21, 50, tzinfo=IST))
    s.fire_one("F1", D)                                         # a retry would fall after 22:00: this was the last chance
    assert len(mail.sent) == 1 and mail.sent[0][1].startswith("Weather update for Mandya (we tried to call you)")
    assert s.messages()[0]["kind"] == KIND_MISSED


def test_no_message_while_a_retry_is_still_to_come(tmp_path):
    s, mail = make(tmp_path, Dial(A.NO_ANSWER, ""))
    s.fire_one("F1", D)                                         # retry planned for 09:30
    assert mail.sent == [] and s.messages() == []


def test_declined_stop_callback_and_provider_failure_get_no_message(tmp_path):
    cases = (Dial(understood="declined"), Dial(understood="no_response", callback="14:15"), Dial(A.FAILED, "", error="boom"))
    for n, dial in enumerate(cases):
        (tmp_path / str(n)).mkdir()
        s, mail = make(tmp_path / str(n), dial, now=datetime(2026, 11, 15, 21, 50, tzinfo=IST))
        s.fire_one("F1", D)
        assert mail.sent == [], n


def test_a_callback_that_is_not_picked_up_sends_the_missed_email(tmp_path):
    s, mail = make(tmp_path, Dial(A.ANSWERED, "no_response", callback="14:15"))
    s.fire_one("F1", D)
    assert mail.sent == []                                      # a callback is booked: nothing yet
    s.dialler = Dial(A.NO_ANSWER, "")
    assert s.run_due_callbacks(datetime(2026, 11, 15, 14, 16, tzinfo=IST)) == 1
    assert len(mail.sent) == 1 and mail.sent[0][1].startswith("Weather update for Mandya (missed call at 14:15)")
    assert "We tried to call you back at 14:15, as you requested" in mail.sent[0][2] and "unfortunately could not reach you" in mail.sent[0][2]
    assert s.messages()[0]["kind"] == KIND_CALLBACK_MISSED


def test_a_callback_that_went_through_sends_the_callback_weather_email(tmp_path):
    s, mail = make(tmp_path, Dial(A.ANSWERED, "no_response", callback="14:15"))
    s.fire_one("F1", D)
    s.dialler = Dial(A.ANSWERED, "yes")
    assert s.run_due_callbacks(datetime(2026, 11, 15, 14, 16, tzinfo=IST)) == 1
    assert len(mail.sent) == 1 and mail.sent[0][1].startswith("Weather update for Mandya") and "Thank you for speaking with us at 14:15" in mail.sent[0][2]
    assert s.messages()[0]["kind"] == KIND_CALLBACK_WEATHER


def test_a_missed_callback_time_sends_the_missed_email(tmp_path):
    s, mail = make(tmp_path, Dial(A.ANSWERED, "no_response", callback="14:15"))
    s.fire_one("F1", D)
    s.run_due_callbacks(datetime(2026, 11, 15, 15, 0, tzinfo=IST))      # 45 minutes late: marked missed, not called
    assert len(mail.sent) == 1 and "14:15" in mail.sent[0][1]


def test_no_email_address_or_no_smtp_settings_is_recorded_not_fatal(tmp_path):
    s, mail = make(tmp_path, Dial())
    s.fire_one("F2", D)                                         # Lakshmi has no email
    assert mail.sent == [] and s.messages()[0]["status"] == "skipped" and "no email" in s.messages()[0]["note"]
    (tmp_path / "n").mkdir()
    s2, _ = make(tmp_path / "n", Dial(), mailer=NullMailer())
    s2.fire_one("F1", D)                                        # an address but no SMTP settings
    assert s2.messages()[0]["status"] == "skipped" and "not set up" in s2.messages()[0]["note"]


def test_a_mail_server_error_is_recorded_by_type_and_the_call_result_is_kept(tmp_path):
    s, _ = make(tmp_path, Dial(), mailer=RecordingMailer(fail=True))
    s.fire_one("F1", D)
    m = s.messages()[0]
    assert m["status"] == "failed" and m["note"] == "ConnectionError"
    assert "@" not in str(s.alerts())
    assert s.calls()[0]["status"]


def test_in_test_mode_every_farmers_message_goes_to_the_one_test_address(tmp_path):
    mail = RecordingMailer()
    s = DashboardService(str(tmp_path / "t.db"), dialler=Dial(), env={"GATE0_WEATHER": "mock", "GATE0_MAIL_TEST_TO": "Tester@Example.com"},
                         now=lambda: T0, mailer=mail)
    s.import_csv(CSV)
    s.ports = s._make_ports()
    s.fire_one("F1", D)
    s.fire_one("F2", D)                                         # Lakshmi has no email of her own: still sent, to the test address
    assert [m[0] for m in mail.sent] == ["tester@example.com"] * 2
    assert mail.sent[0][1].startswith("[Test: Ramesh, F1] ") and mail.sent[1][1].startswith("[Test: Lakshmi, F2] ")
    assert [m["status"] for m in s.messages()] == ["sent", "sent"]


def test_the_email_text_is_english_with_only_the_weather_facts_and_the_subject_follows_the_situation():
    subjects = set()
    for kind in KINDS:
        subject, body, html = build_email("Ramesh", "Mandya", WEATHER, kind, "14:15")
        subjects.add(subject)
        assert "Mandya" in subject and body.startswith("Dear Ramesh,") and "27.5" in body and "40 percent" in body
        assert body.isascii() and "Regards,\nTeam Agrythm" in body
        assert 'src="cid:agrythm-logo"' in html and "14 to 27.5 degrees Celsius" in html
    assert len(subjects) == 3          # the two missed situations have their own subject; the two 'went through' ones share one
    assert "unfortunately could not reach you" in build_email("Ramesh", "Mandya", WEATHER, KIND_MISSED)[1]
    for kind in KINDS:
        assert "prefer not to receive" not in build_email("Ramesh", "Mandya", WEATHER, kind)[1]      # no opt-out line (team, 15 Nov)
    assert "could not reach you" not in build_email("Ramesh", "Mandya", WEATHER, KIND_WEATHER)[1]


def test_names_are_escaped_in_the_html_version():
    html = build_email("<b>Ra&mesh</b>", "Mandya", WEATHER, KIND_WEATHER)[2]
    assert "<b>Ra" not in html and "&lt;b&gt;Ra&amp;mesh&lt;/b&gt;" in html


def test_the_sent_mail_has_text_html_and_the_logo_inside(tmp_path):
    m = SmtpMailer("smtp.example.com", 587, "sender@x.com", "s3cret-app-pass", team="team@x.com")
    subject, text, html = build_email("Ramesh", "Mandya", WEATHER, KIND_WEATHER)
    msg = m.build("to@x.com", subject, text, html)
    assert msg["To"] == "to@x.com" and msg["From"] == "sender@x.com" and msg["Bcc"] == "team@x.com"
    parts = {p.get_content_type(): p for p in msg.walk()}
    assert "text/plain" in parts and "text/html" in parts and parts["image/png"]["Content-ID"] == "<agrythm-logo>"
    assert parts["image/png"].get_payload(decode=True)[:4] == b"\x89PNG"
    assert "s3cret-app-pass" not in msg.as_string()


def test_mailer_choice_and_secrets(monkeypatch):
    assert isinstance(make_mailer({}), NullMailer)
    m = make_mailer({"GATE0_SMTP_HOST": "smtp.example.com", "GATE0_SMTP_USER": "u@x.com", "GATE0_SMTP_PASSWORD": "hunter2"})
    assert isinstance(m, SmtpMailer) and "hunter2" not in repr(m)
