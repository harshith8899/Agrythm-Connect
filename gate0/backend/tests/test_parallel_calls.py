"""Calls are placed at the same time: a hundred farmers do not queue behind one another."""
import threading
import time
from datetime import date, datetime, timedelta

import pytest

from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST

A = AttemptStatus
D = date(2026, 11, 17)
T0 = datetime(2026, 11, 17, 9, 0, tzinfo=IST)


def csv(n):
    rows = ["Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active"]
    for i in range(n):
        rows.append(f"F{i:03d},Farmer {i},98765{i:05d},Mandya,Mandya,Karnataka,Hindi,Yes,Yes")
    return "\n".join(rows) + "\n"


class Slow:
    """Every call takes `seconds` on the phone; records how many were on the phone at once."""
    mode, live = "slow", False

    def __init__(self, seconds=0.4, status=A.ANSWERED, understood="yes"):
        self.seconds, self.status, self.understood = seconds, status, understood
        self.now_on_phone = self.most_at_once = self.total = 0
        self.lock = threading.Lock()

    def place(self, phone, language_name, variables):
        with self.lock:
            self.now_on_phone += 1
            self.total += 1
            self.most_at_once = max(self.most_at_once, self.now_on_phone)
            n = self.total
        time.sleep(self.seconds)
        with self.lock:
            self.now_on_phone -= 1
        return ProviderCallResult(self.status, provider_call_id=f"C{n}", duration_s=30)

    def outputs(self, attempt_id):
        return {"understood_weather": self.understood, "stop_calls_requested": "no", "call_summary": "s", "callback_time": ""}


def make(tmp_path, dialler, farmers, now=T0, **env):
    s = DashboardService(str(tmp_path / "p.db"), dialler=dialler, env={"GATE0_WEATHER": "mock", **env}, now=lambda: now)
    s.async_inbound = False
    s.import_csv(csv(farmers))
    return s


@pytest.mark.parametrize("farmers", [50, 100])
def test_the_daily_send_calls_every_farmer_at_the_same_time(tmp_path, farmers):
    d = Slow(1.5)
    s = make(tmp_path, d, farmers)
    start = time.monotonic()
    s.fire(D)
    took = time.monotonic() - start
    assert d.total == farmers and d.most_at_once >= 0.8 * farmers            # nearly all were on the phone together (starts are a few ms apart)
    assert took < 1.5 * farmers / 4                                           # nowhere near one after the other
    assert sum(1 for c in s.calls() if c["status"] == "Completed") == farmers
    assert s.db.execute("SELECT COUNT(*) FROM dash_live").fetchone()[0] == 0
    assert s.last_run["counts"] == {"called": farmers}


def test_the_number_at_once_can_be_limited_by_a_setting(tmp_path):
    d = Slow(0.3)
    s = make(tmp_path, d, 20, GATE0_MAX_PARALLEL_CALLS="5")
    s.fire(D)
    assert d.total == 20 and d.most_at_once == 5


def test_every_due_retry_and_callback_is_placed_at_the_same_time(tmp_path):
    clock = {"now": T0}
    d = Slow(1.5, A.NO_ANSWER, "")
    s = DashboardService(str(tmp_path / "r.db"), dialler=d, env={"GATE0_WEATHER": "mock"}, now=lambda: clock["now"])
    s.async_inbound = False
    s.import_csv(csv(30))
    s.fire(D)                                                                 # nobody picks up: 30 retries are planned
    assert d.most_at_once >= 24
    d.most_at_once = 0
    clock["now"] = T0 + timedelta(minutes=30)
    start = time.monotonic()
    assert s.run_due_retries() == 30
    assert d.most_at_once >= 24 and time.monotonic() - start < 6
    # callbacks: book 30 for the same minute and place them together
    d.most_at_once = 0
    for i in range(30):
        s._schedule_callback(f"F{i:03d}", D, "16:30", now=clock["now"])
    assert s.run_due_callbacks(datetime(2026, 11, 17, 16, 31, tzinfo=IST)) == 30
    assert d.most_at_once >= 24


def test_a_failing_call_never_stops_the_others_when_they_run_together(tmp_path):
    class Flaky(Slow):
        def place(self, phone, language_name, variables):
            if phone.endswith("00007"):
                raise RuntimeError("provider down")
            return super().place(phone, language_name, variables)

    d = Flaky(0.2)
    s = make(tmp_path, d, 20)
    s.fire(D)
    statuses = [c["status"] for c in s.calls()]
    assert statuses.count("Completed") == 19 and len(statuses) == 20


def test_the_database_connections_stay_few_however_many_calls_run_together(tmp_path):
    d = Slow(1.5)
    s = make(tmp_path, d, 60, GATE0_DB_POOL="3")
    s.fire(D)
    assert d.most_at_once >= 48 and s._ports_made <= 3
