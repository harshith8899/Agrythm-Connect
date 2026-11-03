"""Comprehensive test suite for ACK-17: Automated 9:00 AM Daily Farmer Call Dispatcher."""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from apscheduler.triggers.cron import CronTrigger

from weathercall.adapters.local import InMemoryFarmerSource, SQLiteLedger, demo_farmers
from weathercall.adapters.mock import DEMO_WEATHER, MockTelephony, MockVoice, MockWeather
from weathercall.config import Settings
from weathercall.contracts import (
    AttemptStatus, CallAttempt, DispatchStatus, FarmerContext, FarmerDayResult,
    FinalResult, Language, ProviderCallResult, SkipReason, WeatherReport,
)
from weathercall.dispatcher import BIDAR_LAT, BIDAR_LON, BIDAR_PLACE, DailyFarmerDispatcher
from weathercall.engine import Ports
from weathercall.scheduler import JOB_ID, create_scheduler

RUN_DATE = date(2026, 11, 5)


def make_test_ports(
    farmers: list[FarmerContext] | None = None,
    weather_dict: dict[str, WeatherReport] | None = None,
    script: dict[str, list[AttemptStatus]] | None = None,
    ledger: SQLiteLedger | None = None,
) -> Ports:
    """Helper to build test ports with in-memory SQLite and offline mocks."""
    w_dict = weather_dict if weather_dict is not None else {
        BIDAR_PLACE: WeatherReport(
            BIDAR_PLACE, "partly cloudy", 20, 31, 15, "mock-open-meteo", wind_speed_kmh=12.5, humidity_pct=60
        )
    }
    return Ports(
        farmers=InMemoryFarmerSource(farmers if farmers is not None else demo_farmers()),
        ledger=ledger or SQLiteLedger(":memory:"),
        weather=MockWeather(w_dict),
        voice=MockVoice(),
        telephony=MockTelephony(script),
    )


# 1. Dispatcher starts and executes successfully
def test_1_dispatcher_starts_and_executes_successfully():
    ports = make_test_ports()
    dispatcher = DailyFarmerDispatcher(ports=ports)
    summary = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)

    assert summary.status == "completed"
    assert summary.weather_fetched is True
    assert summary.dispatch_date == RUN_DATE
    # 10 demo farmers minus 1 inactive (F009), 1 no-consent (F008) = 8 eligible farmers
    assert summary.total_eligible == 8
    assert summary.submitted == 8
    assert summary.failed == 0
    assert summary.skipped_duplicates == 0
    assert summary.skipped_ineligible == 2

    # Verify records stored in SQLite database
    dispatches = ports.ledger.db.execute("SELECT farmer_id, status FROM daily_dispatches").fetchall()
    assert len(dispatches) == 8
    for fid, status in dispatches:
        assert status == DispatchStatus.COMPLETED.value


# 2. Weather API failure
def test_2_weather_api_failure_aborts_dispatch():
    # Empty weather dictionary: Bidar weather will return None
    ports = make_test_ports(weather_dict={})
    dispatcher = DailyFarmerDispatcher(ports=ports)
    summary = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)

    assert summary.status == "aborted_weather_unavailable"
    assert summary.weather_fetched is False
    assert summary.submitted == 0
    assert summary.failed == 0
    # Telephony must NEVER be called if weather fails (no fabricated or stale data)
    assert len(ports.telephony._count) == 0

    # Ensure no calls were dispatched in SQLite
    dispatches = ports.ledger.db.execute("SELECT COUNT(*) FROM daily_dispatches").fetchone()[0]
    assert dispatches == 0


# 3. Empty farmer list
def test_3_empty_farmer_list_completes_cleanly():
    ports = make_test_ports(farmers=[])
    dispatcher = DailyFarmerDispatcher(ports=ports)
    summary = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)

    assert summary.status == "completed"
    assert summary.weather_fetched is True
    assert summary.total_eligible == 0
    assert summary.submitted == 0
    assert summary.failed == 0
    assert len(ports.telephony._count) == 0


# 4. Multiple eligible farmers
def test_4_multiple_eligible_farmers_all_dispatched():
    farmers = [
        FarmerContext("F101", "Basappa", Language.KN, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "FAKE-9001"),
        FarmerContext("F102", "Shivaji", Language.HI, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "FAKE-9002"),
        FarmerContext("F103", "Anand", Language.EN, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "FAKE-9003"),
    ]
    ports = make_test_ports(farmers=farmers)
    dispatcher = DailyFarmerDispatcher(ports=ports)
    summary = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)

    assert summary.status == "completed"
    assert summary.total_eligible == 3
    assert summary.submitted == 3
    assert summary.failed == 0

    # Verify each farmer received a call with registered phone
    assert "FAKE-9001" in ports.telephony._count
    assert "FAKE-9002" in ports.telephony._count
    assert "FAKE-9003" in ports.telephony._count

    # Verify languages were passed to voice synthesizer in attempts table
    attempts = ports.ledger.db.execute("SELECT farmer_id, language FROM attempts ORDER BY farmer_id").fetchall()
    assert attempts == [("F101", "kn"), ("F102", "hi"), ("F103", "en")]


# 5. Duplicate daily dispatch prevention
def test_5_duplicate_daily_dispatch_prevention():
    ports = make_test_ports()
    dispatcher = DailyFarmerDispatcher(ports=ports)

    # First run
    summary1 = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)
    assert summary1.submitted == 8
    call_counts_run1 = dict(ports.telephony._count)

    # Second run on the same date
    summary2 = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)
    assert summary2.submitted == 0
    assert summary2.skipped_duplicates == 8

    # Telephony was NOT called again on second run
    assert ports.telephony._count == call_counts_run1

    # Verify database UNIQUE(farmer_id, dispatch_date) constraint
    with pytest.raises(sqlite3.IntegrityError):
        ports.ledger.create_daily_dispatch("F001", RUN_DATE, "accepted")


# 6. Telephony provider request failure
def test_6_telephony_provider_request_failure_recorded():
    farmers = [
        FarmerContext("F201", "Sharan", Language.KN, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "FAKE-FAIL-01")
    ]
    # Telephony always returns FAILED for this phone
    ports = make_test_ports(farmers=farmers, script={"FAKE-FAIL-01": [AttemptStatus.FAILED]})
    dispatcher = DailyFarmerDispatcher(ports=ports)
    summary = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)

    assert summary.status == "completed_with_failures"
    assert summary.submitted == 1
    assert summary.failed == 1

    # Verify daily dispatch record marked as failed
    disp = ports.ledger.get_daily_dispatch("F201", RUN_DATE)
    assert disp is not None
    assert disp["status"] == "failed"
    assert disp["error"] == "mock_failure"


# 7. One farmer's failure does not stop other farmers
def test_7_one_farmer_failure_does_not_stop_batch():
    class ExceptionTelephony(MockTelephony):
        def place_call(self, phone: str, audio_ref: str) -> ProviderCallResult:
            if phone == "FAKE-CRASH":
                raise RuntimeError("Provider gateway crash")
            return super().place_call(phone, audio_ref)

    farmers = [
        FarmerContext("F301", "Farmer 1", Language.EN, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "FAKE-OK-1"),
        FarmerContext("F302", "Farmer 2", Language.KN, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "FAKE-CRASH"),
        FarmerContext("F303", "Farmer 3", Language.HI, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "FAKE-OK-2"),
    ]
    ports = Ports(
        farmers=InMemoryFarmerSource(farmers),
        ledger=SQLiteLedger(":memory:"),
        weather=MockWeather({BIDAR_PLACE: WeatherReport(BIDAR_PLACE, "clear", 22, 32, 0, "mock")}),
        voice=MockVoice(),
        telephony=ExceptionTelephony(),
    )
    dispatcher = DailyFarmerDispatcher(ports=ports)
    summary = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)

    # Batch finished all 3 farmers
    assert summary.total_eligible == 3
    assert summary.submitted == 3
    assert summary.failed == 1

    # Farmer 1 and Farmer 3 completed successfully
    assert ports.ledger.get_daily_dispatch("F301", RUN_DATE)["status"] == "completed"
    assert ports.ledger.get_daily_dispatch("F302", RUN_DATE)["status"] == "failed"
    assert ports.ledger.get_daily_dispatch("F303", RUN_DATE)["status"] == "completed"


# 8. Scheduler configured for 9:00 AM Asia/Kolkata
def test_8_scheduler_configured_for_9am_asia_kolkata():
    ports = make_test_ports()
    dispatcher = DailyFarmerDispatcher(ports=ports)
    scheduler = create_scheduler(dispatcher=dispatcher, hour=9, minute=0, tz_name="Asia/Kolkata", blocking=False)

    job = scheduler.get_job(JOB_ID)
    assert job is not None
    assert job.id == "daily_farmer_dispatcher"
    assert isinstance(job.trigger, CronTrigger)

    # Check timezone and trigger fields
    assert str(job.trigger.timezone) == "Asia/Kolkata"
    field_map = {f.name: str(f) for f in job.trigger.fields}
    assert field_map["hour"] == "9"
    assert field_map["minute"] == "0"


# 9. Scheduler restart does not create duplicate calls
def test_9_scheduler_restart_does_not_create_duplicate_calls():
    # Shared persistent ledger simulating service restart
    shared_ledger = SQLiteLedger(":memory:")
    ports1 = make_test_ports(ledger=shared_ledger)

    # First run with Dispatcher 1
    disp1 = DailyFarmerDispatcher(ports=ports1, instance_id="scheduler-instance-1")
    s1 = disp1.dispatch_daily_calls(call_date=RUN_DATE)
    assert s1.submitted == 8

    # Scheduler process restarts -> creates new Dispatcher instance 2 with new instance_id
    ports2 = make_test_ports(ledger=shared_ledger)
    disp2 = DailyFarmerDispatcher(ports=ports2, instance_id="scheduler-instance-2")
    s2 = disp2.dispatch_daily_calls(call_date=RUN_DATE)

    # Instance 2 safely detects all farmers already dispatched
    assert s2.submitted == 0
    assert s2.skipped_duplicates == 8


# 10. Existing retry workflow remains unaffected
def test_10_existing_retry_workflow_preserved():
    # Farmer needs 3 attempts: [NO_ANSWER, NO_ANSWER, ANSWERED]
    farmers = [
        FarmerContext("F401", "Jagadish", Language.KN, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "FAKE-RETRY-01")
    ]
    script = {"FAKE-RETRY-01": [AttemptStatus.NO_ANSWER, AttemptStatus.NO_ANSWER, AttemptStatus.ANSWERED]}
    ports = make_test_ports(farmers=farmers, script=script)

    retry_gaps: list[int] = []
    dispatcher = DailyFarmerDispatcher(
        ports=ports,
        settings=Settings(max_attempts=3, retry_gap_minutes=30),
        wait_fn=lambda mins: retry_gaps.append(mins),
    )
    summary = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)

    assert summary.status == "completed"
    assert summary.submitted == 1
    assert summary.failed == 0

    # Exactly 2 retry intervals of 30 minutes each
    assert retry_gaps == [30, 30]

    # 3 attempts recorded in attempts table
    attempts = ports.ledger.db.execute("SELECT attempt_no, status FROM attempts WHERE farmer_id='F401'").fetchall()
    assert len(attempts) == 3
    assert attempts[0] == (1, "no_answer")
    assert attempts[1] == (2, "no_answer")
    assert attempts[2] == (3, "answered")

    # Final day result is ANSWERED after 3 attempts
    day_res = ports.ledger.status(RUN_DATE)
    assert day_res.answered == 1
    assert day_res.rows[0].attempts == 3
    assert day_res.rows[0].result is FinalResult.ANSWERED
