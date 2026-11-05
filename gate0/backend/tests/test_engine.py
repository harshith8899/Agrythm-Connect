from datetime import date

import pytest

from weathercall.adapters.local import InMemoryFarmerSource, SQLiteLedger, demo_farmers
from weathercall.adapters.mock import MockTelephony, MockVoice, MockWeather
from weathercall.config import Settings
from weathercall.contracts import AttemptStatus as S, CallRequest, FinalResult, SkipReason
from weathercall.engine import Ports, process_request, run_morning

D = date(2026, 11, 5)


def make(script=None, farmers=None, settings=None):
    ports = Ports(InMemoryFarmerSource(farmers or demo_farmers()), SQLiteLedger(), MockWeather(), MockVoice(),
                  MockTelephony(script))
    return ports, settings or Settings()


def result_of(view, fid):
    return next(r for r in view.rows if r.farmer_id == fid)


def test_full_morning_counts():
    ports, st = make({"FAKE-0004": [S.NO_ANSWER], "FAKE-0005": [S.FAILED], "FAKE-0003": [S.BUSY, S.ANSWERED]})
    v = run_morning(D, ports, st)
    assert (v.total, v.answered, v.unanswered, v.failed, v.skipped) == (10, 5, 1, 1, 3)
    assert result_of(v, "F003").attempts == 2 and result_of(v, "F003").result is FinalResult.ANSWERED
    assert result_of(v, "F004").attempts == 3 and result_of(v, "F004").result is FinalResult.UNANSWERED
    assert result_of(v, "F005").result is FinalResult.FAILED


def test_skip_reasons():
    ports, st = make()
    v = run_morning(D, ports, st)
    assert result_of(v, "F007").skip_reason is SkipReason.NO_WEATHER
    assert result_of(v, "F008").skip_reason is SkipReason.NO_CONSENT
    assert result_of(v, "F009").skip_reason is SkipReason.INACTIVE


def test_no_dial_without_consent():
    ports, st = make()
    run_morning(D, ports, st)
    assert "FAKE-0008" not in ports.telephony._count and "FAKE-0009" not in ports.telephony._count


def test_second_run_does_not_call_again():
    ports, st = make()
    run_morning(D, ports, st)
    calls = dict(ports.telephony._count)
    v = run_morning(D, ports, st)
    assert ports.telephony._count == calls and v.total == 10


def test_request_for_already_called_farmer_is_reported_not_redialled():
    ports, st = make()
    process_request(CallRequest("F001", D), ports, st)
    r = process_request(CallRequest("F001", D), ports, st)
    assert r.skip_reason is SkipReason.ALREADY_CALLED and ports.telephony._count["FAKE-0001"] == 1


def test_waits_between_attempts_only():
    ports, st = make({"FAKE-0001": [S.NO_ANSWER, S.NO_ANSWER, S.ANSWERED]})
    waits = []
    process_request(CallRequest("F001", D), ports, st, wait=waits.append)
    assert waits == [st.retry_gap_minutes] * 2


def test_provider_exception_becomes_failed_attempt_without_leaking_details():
    class Boom:
        def place_call(self, phone, audio_ref):
            raise RuntimeError(f"cannot reach {phone}")
    ports, st = make()
    ports.telephony = Boom()
    r = process_request(CallRequest("F001", D), ports, st)
    assert r.result is FinalResult.FAILED
    err = ports.ledger.db.execute("SELECT error FROM attempts").fetchone()[0]
    assert err == "RuntimeError" and "FAKE" not in err


def test_status_view_and_logs_hold_no_phone_numbers():
    ports, st = make()
    v = run_morning(D, ports, st)
    assert "FAKE-" not in repr(v)
    assert all("FAKE-" not in repr(f) for f in demo_farmers())


def test_unsupported_weather_missing_policy_is_loud():
    ports, st = make(settings=Settings(on_weather_missing="generic"))
    with pytest.raises(ValueError):
        process_request(CallRequest("F001", D), ports, st)
