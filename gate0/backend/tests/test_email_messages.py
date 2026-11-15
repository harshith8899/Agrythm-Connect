"""The written message (email) after a call: when it is sent, what it says, and that it never goes twice."""
from datetime import date, datetime

from weathercall.adapters.mailer import NullMailer, RecordingMailer, SmtpMailer, make_mailer
from weathercall.contracts import AttemptStatus, Language, ProviderCallResult
from weathercall.messages import KIND_MISSED, KIND_WEATHER, build_email
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
    assert "हमने" not in body                                   # the 'we tried to reach you' line is only for a missed call
    assert s._send_message("F1", D, KIND_WEATHER) == "not sent: already sent"      # never twice for the same day
    assert [m["status"] for m in s.messages()] == ["sent"]


def test_the_last_failed_attempt_sends_a_we_tried_to_reach_you_email(tmp_path):
    s, mail = make(tmp_path, Dial(A.NO_ANSWER, ""), now=datetime(2026, 11, 15, 21, 50, tzinfo=IST))
    s.fire_one("F1", D)                                         # a retry would fall after 22:00: this was the last chance
    assert len(mail.sent) == 1 and mail.sent[0][1].startswith("हमने")
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
    assert len(mail.sent) == 1 and mail.sent[0][1].startswith("हमने")


def test_a_missed_callback_time_sends_the_missed_email(tmp_path):
    s, mail = make(tmp_path, Dial(A.ANSWERED, "no_response", callback="14:15"))
    s.fire_one("F1", D)
    s.run_due_callbacks(datetime(2026, 11, 15, 15, 0, tzinfo=IST))      # 45 minutes late: marked missed, not called
    assert len(mail.sent) == 1


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


def test_the_email_text_is_in_the_farmers_language_with_only_the_weather_facts():
    for lang in Language:
        subject, body = build_email("Ramesh", lang, "Mandya", WEATHER, KIND_WEATHER)
        assert "Mandya" in subject and "27.5" in body and "14" in body and "Ramesh" in body
    en = build_email("Ramesh", Language.EN, "Mandya", WEATHER, KIND_MISSED)[1]
    assert "tried to call you" in en


def test_mailer_choice_and_secrets(monkeypatch):
    assert isinstance(make_mailer({}), NullMailer)
    m = make_mailer({"GATE0_SMTP_HOST": "smtp.example.com", "GATE0_SMTP_USER": "u@x.com", "GATE0_SMTP_PASSWORD": "hunter2"})
    assert isinstance(m, SmtpMailer) and "hunter2" not in repr(m)
