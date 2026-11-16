"""The Sarvam credit balance: Sarvam has no API for it, so it is the 'Credits Left' figure a person saved, minus the
estimated spend on the call records since then."""
import json
import threading
import urllib.request
from datetime import timedelta
from http.server import ThreadingHTTPServer

import pytest

from test_system import FakeUsage, NOW, attempt, system
from weathercall.server import make_handler


def test_no_balance_until_one_is_saved(tmp_path):
    assert system(tmp_path, FakeUsage()).usage()["balance"] is None


def test_the_balance_is_the_saved_figure_minus_the_spend_since_then(tmp_path):
    # saved 1000 two hours ago. Since then: a 90 s call (2 min x 3.5 = 7, telephony 3 pulses x 0.2 = 0.6) and a call
    # not picked up (free). Before it: a 45 s call that must NOT count.
    s = system(tmp_path, FakeUsage([attempt(300, "connected", 45), attempt(60, "connected", 90), attempt(30, "no_answer", 0)]))
    s.set_balance(1000, at=NOW - timedelta(minutes=120))
    b = s.usage(refresh=True)["balance"]
    assert b["checkpoint"] == 1000 and b["spent"] == 7.6 and b["remaining"] == 992.4
    assert b["estimated"] is True and b["low"] is False and b["partial"] is False


def test_the_balance_falls_as_calls_are_made_and_warns_when_low(tmp_path):
    usage = FakeUsage()
    s = system(tmp_path, usage)
    s.set_balance(105, at=NOW - timedelta(minutes=120))
    assert s.usage(refresh=True)["balance"]["remaining"] == 105 and not s.usage()["balance"]["low"]
    usage.attempts.append(attempt(10, "connected", 60))                     # 1 min = 3.5, telephony 2 pulses = 0.4
    b = s.usage(refresh=True)["balance"]
    assert b["remaining"] == 101.1
    usage.attempts += [attempt(5, "connected", 60)] * 2
    assert s.usage(refresh=True)["balance"]["low"] is True


def test_saving_a_new_figure_restarts_the_count(tmp_path):
    s = system(tmp_path, FakeUsage([attempt(60, "connected", 90)]))
    s.set_balance(500, at=NOW - timedelta(minutes=120))
    assert s.usage(refresh=True)["balance"]["remaining"] == 492.4
    assert s.set_balance(480)["balance"]["remaining"] == 480


def test_without_call_records_the_checkpoint_is_shown_not_a_guess(tmp_path):
    s = system(tmp_path, FakeUsage(error=RuntimeError("HTTP 502")))
    b = s.set_balance(500)["balance"]
    assert b["checkpoint"] == 500 and b["remaining"] is None and b["spent"] is None


@pytest.mark.parametrize("bad", [None, True, "abc", -1, float("inf"), 1e12])
def test_a_bad_balance_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        system(tmp_path, FakeUsage()).set_balance(bad)


def test_the_balance_is_saved_through_the_api(tmp_path):
    s = system(tmp_path, FakeUsage([attempt(5, "connected", 60)]))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(s.service, {"*"}, s))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/usage", method="POST",
                                     data=json.dumps({"sarvam_balance": 250}).encode(),
                                     headers={"Content-Type": "application/json"})
        body = json.loads(urllib.request.urlopen(req).read())
        assert body["balance"]["checkpoint"] == 250
    finally:
        server.shutdown()
