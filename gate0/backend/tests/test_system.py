import json
import threading
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest

from weathercall.adapters.dialers import MockDialler
from weathercall.server import make_handler
from weathercall.service import DashboardService, IST
from weathercall.system import SystemChecks, billed_minutes

UTC = timezone.utc
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=IST)          # 06:30 UTC


def attempt(minutes_ago, status="connected", seconds=45, reason=None, version=9):
    at = (NOW - timedelta(minutes=minutes_ago)).astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    return {"attempted_at": at, "connectivity_status": status, "duration_in_seconds": seconds,
            "failure_reason": reason, "app_version": version}


class FakeUsage:
    app_version = 9

    def __init__(self, attempts=(), error=None):
        self.attempts, self.error = list(attempts), error

    def attempts_between(self, start, end):
        if self.error:
            raise self.error
        return list(self.attempts)


class FakeWeather:
    def __init__(self, error=None, empty=False):
        self.error, self.empty, self.calls = error, empty, 0

    def get_forecast(self, place, lat, lon, start):
        self.calls += 1
        if self.error:
            raise self.error
        return {} if self.empty else {start: object()}


def service(tmp_path):
    return DashboardService(str(tmp_path / "s.db"), dialler=MockDialler(), env={"GATE0_WEATHER": "mock"}, now=lambda: NOW)


def system(tmp_path, usage=None, weather=None, name="s.db"):
    svc = DashboardService(str(tmp_path / name), dialler=MockDialler(), env={"GATE0_WEATHER": "mock"}, now=lambda: NOW)
    return SystemChecks(svc, usage=usage, weather=weather or FakeWeather(), now=lambda: NOW)


# ---- billing rules (from Sarvam's pricing page) --------------------------------------------------------------------
@pytest.mark.parametrize("seconds, minutes", [(0, 0), (1, 1), (45, 1), (60, 1), (61, 2), (125, 3)])
def test_a_call_is_billed_in_started_minutes(seconds, minutes):
    assert billed_minutes("connected", seconds) == minutes


def test_calls_that_never_connected_cost_nothing():
    for status in ("no_answer", "busy", "failed"):
        assert billed_minutes(status, 30) == 0


# ---- usage (real call records only; the balance itself is only on Sarvam's Billing page) ------------------------------
def test_without_sarvam_there_is_no_usage_to_show(tmp_path):
    u = system(tmp_path).usage()
    assert u["configured"] is False and u["window"] is None and u["days"] == []


def test_usage_counts_calls_and_billed_minutes_from_sarvams_records(tmp_path):
    attempts = [attempt(10, seconds=45), attempt(20, seconds=61), attempt(30, "no_answer", 0), attempt(40, "busy", 0),
                attempt(60 * 24 * 3, seconds=125),                  # three days ago: in the week, not today
                attempt(60 * 24 * 20, seconds=30)]                  # twenty days ago: in the window only
    u = system(tmp_path, FakeUsage(attempts)).usage()
    assert u["today"] == {"calls": 4, "connected": 2, "billed_minutes": 3, "amount": 10.5}      # 45 s -> 1, 61 s -> 2
    assert u["week"] == {"calls": 5, "connected": 3, "billed_minutes": 6, "amount": 21.0}       # + 125 s -> 3
    assert u["window"] == {"calls": 6, "connected": 4, "billed_minutes": 7, "amount": 24.5}
    assert u["rate"] == 3.5 and u["currency"] == "INR"                                          # Sarvam pay-as-you-go
    assert set(u["today"]) == {"calls", "connected", "billed_minutes", "amount"}     # an estimate; there is still no balance


def test_daily_breakdown_is_by_india_date(tmp_path):
    s = system(tmp_path, FakeUsage([attempt(10, seconds=30), attempt(60 * 24 + 10, seconds=130)]))
    days = s.usage()["days"]
    assert [d["date"] for d in days] == ["2026-11-06", "2026-11-05"]
    assert days[0]["billed_minutes"] == 1 and days[1]["billed_minutes"] == 3
    assert days[0]["amount"] == 3.5 and days[1]["amount"] == 10.5


def test_exhausted_credits_are_spotted_from_sarvams_error(tmp_path):
    s = system(tmp_path, FakeUsage([attempt(5, "failed", 0, '{"error":{"code":402,"type":"insufficient_quota_error"}}')]))
    assert s.usage()["exhausted"] is True
    assert system(tmp_path, FakeUsage([attempt(5, "failed", 0, "exotel: not KYC compliant")]), name="b.db").usage()["exhausted"] is False


def test_the_rate_can_be_changed_and_the_amounts_follow(tmp_path):
    s = system(tmp_path, FakeUsage([attempt(10, seconds=45), attempt(20, seconds=61)]))
    assert s.usage()["today"]["amount"] == 10.5
    u = s.set_rate(3.15)                                              # a cheaper plan
    assert u["rate"] == 3.15 and u["today"]["amount"] == 9.45 and u["days"][0]["amount"] == 9.45
    assert s.usage()["rate"] == 3.15                                  # kept


@pytest.mark.parametrize("bad", [-1, 0, "abc", None, True, float("inf"), 100000])
def test_a_bad_rate_is_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        system(tmp_path).set_rate(bad)


def test_a_sarvam_error_is_reported_not_raised(tmp_path):
    u = system(tmp_path, FakeUsage(error=RuntimeError("Sarvam API returned HTTP 401"))).usage()
    assert u["configured"] is True and "401" in u["error"] and u["window"] is None


# ---- connection checks -----------------------------------------------------------------------------------------------
def by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_everything_ok(tmp_path):
    s = system(tmp_path, FakeUsage([attempt(5)]))
    s.service.import_csv("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent\n"
                         "F1,A,9876543210,Mandya,Mandya,Karnataka,Hindi,Yes\n")
    r = s.checks()
    c = by_id(r)
    assert r["overall"] == "ok" and [x["id"] for x in r["checks"]] == ["backend", "database", "weather", "sarvam", "phone"]
    assert all(x["status"] == "ok" for x in r["checks"])
    assert "1 farmers" in c["database"]["detail"] and "version 9" in c["sarvam"]["detail"]
    assert "connected" in c["phone"]["detail"].lower()


def test_weather_api_down_is_reported_without_stopping_the_other_checks(tmp_path):
    r = system(tmp_path, FakeUsage([attempt(5)]), FakeWeather(error=TimeoutError("slow"))).checks()
    c = by_id(r)
    assert r["overall"] == "fail" and c["weather"]["status"] == "fail" and "TimeoutError" in c["weather"]["detail"]
    assert c["backend"]["status"] == "ok" and c["database"]["status"] == "ok" and c["sarvam"]["status"] == "ok"


def test_weather_that_answers_without_today_is_a_failure(tmp_path):
    assert by_id(system(tmp_path, FakeUsage(), FakeWeather(empty=True)).checks())["weather"]["status"] == "fail"


def test_sarvam_key_rejected_is_a_failure_with_the_reason(tmp_path):
    err = RuntimeError("Sarvam API returned HTTP 401 unauthorized")
    c = by_id(system(tmp_path, FakeUsage(error=err)).checks())
    assert c["sarvam"]["status"] == "fail" and "401" in c["sarvam"]["detail"]
    assert c["phone"]["status"] == "off"


def test_phone_line_failure_shows_the_reason_but_never_a_phone_number(tmp_path):
    reason = 'exotel: {"Message":"Your account is not yet KYC compliant. Call +919876543210"}'
    c = by_id(system(tmp_path, FakeUsage([attempt(5, "failed", 0, reason)])).checks())
    assert c["phone"]["status"] == "fail" and "KYC" in c["phone"]["detail"] and "9876543210" not in c["phone"]["detail"]


def test_not_configured_is_off_not_failed(tmp_path):
    r = system(tmp_path).checks()
    c = by_id(r)
    assert c["sarvam"]["status"] == "off" and c["phone"]["status"] == "off" and r["overall"] == "ok"


def test_checks_are_cached_briefly_and_refresh_forces_a_new_run(tmp_path):
    w = FakeWeather()
    s = system(tmp_path, FakeUsage(), w)
    s.checks()
    s.checks()
    assert w.calls == 1
    s.checks(refresh=True)
    assert w.calls == 2


# ---- API -------------------------------------------------------------------------------------------------------------
@pytest.fixture
def api(tmp_path):
    s = system(tmp_path, FakeUsage([attempt(5, seconds=45)]))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(s.service, {"*"}, s))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, data=None):
        req = urllib.request.Request(base + path, data=data, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)
    yield call
    srv.shutdown()


def test_api_checks_and_usage(api):
    code, body = api("/api/system/checks")
    assert code == 200 and body["overall"] == "ok" and len(body["checks"]) == 5
    code, body = api("/api/usage")
    assert code == 200 and body["today"]["billed_minutes"] == 1
    assert body["rate"] == 3.5 and body["today"]["amount"] == 3.5
    code, body = api("/api/usage", json.dumps({"sarvam_rate": 3.25}).encode())
    assert code == 200 and body["rate"] == 3.25 and body["today"]["amount"] == 3.25
    assert api("/api/usage", json.dumps({"sarvam_rate": -2}).encode())[0] == 400
    assert api("/api/usage", b"nope")[0] == 400
    assert api("/api/credits")[0] == 404                       # there is no balance to read or set


# ---- where the backend runs ---------------------------------------------------------------------------------------------------
def test_the_backend_check_says_it_is_hosted_on_render(tmp_path):
    svc = DashboardService(str(tmp_path / "r.db"), dialler=MockDialler(), env={"GATE0_WEATHER": "mock"}, now=lambda: NOW)
    hosted = {"RENDER": "true", "RENDER_SERVICE_NAME": "agrythm-connect", "RENDER_GIT_COMMIT": "abcdef1234567"}
    c = by_id(SystemChecks(svc, usage=None, weather=FakeWeather(), now=lambda: NOW, env=hosted).checks())["backend"]
    assert "Hosted on Render (agrythm-connect, version abcdef1)" in c["detail"] and "computer" not in c["detail"]


def test_the_backend_check_says_when_it_is_not_on_render(tmp_path):
    c = by_id(system(tmp_path, FakeUsage([attempt(5)])).checks())["backend"]
    assert "Running on a computer, not on Render" in c["detail"]


def test_the_weather_check_names_the_http_code_when_open_meteo_refuses(tmp_path):
    import urllib.error
    for code, words in ((429, "too many requests"), (403, "blocked"), (500, "HTTP 500")):
        err = urllib.error.HTTPError("https://api.open-meteo.com", code, "x", {}, None)
        c = by_id(system(tmp_path, FakeUsage(), FakeWeather(error=err), name=f"w{code}.db").checks())["weather"]
        assert c["status"] == "fail" and f"HTTP {code}" in c["detail"] and words in c["detail"]


def test_the_weather_check_says_which_service_is_used_and_names_a_rejected_key(tmp_path):
    import urllib.error

    class Keyed(FakeWeather):
        uses_key = True

    ok = by_id(system(tmp_path, FakeUsage(), Keyed(), name="k1.db").checks())["weather"]
    assert ok["status"] == "ok" and "paid API key" in ok["detail"]
    assert "free service" in by_id(system(tmp_path, FakeUsage(), FakeWeather(), name="k2.db").checks())["weather"]["detail"]
    bad = Keyed(error=urllib.error.HTTPError("https://customer-api.open-meteo.com", 401, "x", {}, None))
    c = by_id(system(tmp_path, FakeUsage(), bad, name="k3.db").checks())["weather"]
    assert c["status"] == "fail" and "key was rejected" in c["detail"] and "customer-api" not in c["detail"]
