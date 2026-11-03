"""Automated daily farmer call dispatcher for Agrythm Connect (ACK-17).

Triggers daily at 9:00 AM IST (Asia/Kolkata), fetches Bidar weather,
verifies farmer eligibility, checks duplicate dispatch constraints,
submits calls via telephony, and logs execution summaries.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .config import Settings
from .contracts import (
    AttemptStatus, CallAttempt, DispatchStatus, DispatchSummary,
    FarmerContext, FarmerDayResult, FinalResult, Language, ProviderCallResult,
    SkipReason, WeatherReport,
)
from .engine import Ports
from .script import build_message

logger = logging.getLogger("weathercall.dispatcher")

# Bidar District coordinates (Karnataka, India)
BIDAR_PLACE = "Bidar"
BIDAR_LAT = 17.9104
BIDAR_LON = 77.5199
IST_TIMEZONE = ZoneInfo("Asia/Kolkata")


class DailyFarmerDispatcher:
    """Orchestrates daily morning weather phone calls for registered farmers in Bidar."""

    def __init__(
        self,
        ports: Ports | None = None,
        settings: Settings | None = None,
        instance_id: str | None = None,
        wait_fn: Callable[[int], None] | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        if ports is None:
            from .adapters import build_ports
            ports = build_ports()
        self.ports = ports
        self.settings = settings or Settings.from_env()
        self.instance_id = instance_id or f"dispatcher-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.wait_fn = wait_fn or (lambda minutes: None)
        self.logger = log or logger

    def dispatch_daily_calls(self, call_date: date | None = None) -> DispatchSummary:
        """Execute the 9:00 AM IST daily call dispatch run."""
        start_dt = datetime.now(timezone.utc)
        start_time_iso = start_dt.isoformat()

        if call_date is None:
            call_date = datetime.now(IST_TIMEZONE).date()

        self.logger.info(
            f"[DISPATCHER-START] Daily farmer call dispatch initiated for date: {call_date.isoformat()} "
            f"(Instance ID: {self.instance_id})"
        )

        # 1. Multi-instance lock protection
        lock_name = f"daily_farmer_dispatcher:{call_date.isoformat()}"
        acquired = self.ports.ledger.acquire_lock(lock_name, self.instance_id)
        if not acquired:
            self.logger.warning(
                f"[DISPATCHER-LOCK] Lock '{lock_name}' is held by another active scheduler instance. "
                "Skipping duplicate execution to prevent multiple workers from calling farmers simultaneously."
            )
            end_dt = datetime.now(timezone.utc)
            return DispatchSummary(
                dispatch_date=call_date,
                start_time=start_time_iso,
                end_time=end_dt.isoformat(),
                duration_s=(end_dt - start_dt).total_seconds(),
                status="locked_by_another_instance",
                weather_fetched=False,
                total_eligible=0,
                submitted=0,
                failed=0,
                skipped_duplicates=0,
                skipped_ineligible=0,
            )

        try:
            return self._run_dispatch(call_date, start_dt, start_time_iso)
        finally:
            self.ports.ledger.release_lock(lock_name, self.instance_id)

    def _run_dispatch(
        self,
        call_date: date,
        start_dt: datetime,
        start_time_iso: str,
    ) -> DispatchSummary:
        # 2. Fetch Bidar weather once
        self.logger.info(
            f"[DISPATCHER-WEATHER] Fetching weather forecast for {BIDAR_PLACE} "
            f"({BIDAR_LAT:.4f}, {BIDAR_LON:.4f}) on {call_date.isoformat()}..."
        )
        weather_report: WeatherReport | None = None
        try:
            weather_report = self.ports.weather.get_weather(BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, call_date)
        except Exception as exc:
            self.logger.error(
                f"[DISPATCHER-WEATHER-ERROR] Unexpected exception querying weather provider: {exc}",
                exc_info=True,
            )
            weather_report = None

        if weather_report is None:
            self.logger.error(
                f"[DISPATCHER-ABORT] Weather API unavailable or returned invalid data for {BIDAR_PLACE} on {call_date}. "
                "Aborting daily dispatch run without initiating calls to prevent delivering fabricated or stale data."
            )
            end_dt = datetime.now(timezone.utc)
            return DispatchSummary(
                dispatch_date=call_date,
                start_time=start_time_iso,
                end_time=end_dt.isoformat(),
                duration_s=(end_dt - start_dt).total_seconds(),
                status="aborted_weather_unavailable",
                weather_fetched=False,
                total_eligible=0,
                submitted=0,
                failed=0,
                skipped_duplicates=0,
                skipped_ineligible=0,
            )

        self.logger.info(
            f"[DISPATCHER-WEATHER-OK] Weather report acquired from '{weather_report.source}': "
            f"Summary='{weather_report.summary}', Temps={weather_report.temp_min_c}°C-{weather_report.temp_max_c}°C, "
            f"Rain={weather_report.rain_chance_pct}%, Wind={weather_report.wind_speed_kmh}km/h, "
            f"Humidity={weather_report.humidity_pct}%"
        )

        # 3. Retrieve eligible farmers
        candidate_ids = self.ports.farmers.list_callable_ids(call_date)
        self.logger.info(
            f"[DISPATCHER-FARMERS] Found {len(candidate_ids)} candidate farmer records in database."
        )

        total_eligible = 0
        submitted = 0
        failed = 0
        skipped_duplicates = 0
        skipped_ineligible = 0
        details: list[dict[str, Any]] = []

        for fid in candidate_ids:
            farmer = self.ports.farmers.get_context(fid)

            # Eligibility validations
            if farmer is None or not farmer.active:
                self.logger.info(f"[DISPATCHER-SKIP] Farmer {fid} skipped: inactive or missing record.")
                skipped_ineligible += 1
                if not self.ports.ledger.has_final_result(fid, call_date):
                    self.ports.ledger.record_day_result(
                        FarmerDayResult(fid, call_date, FinalResult.SKIPPED, 0, SkipReason.INACTIVE)
                    )
                continue

            if not farmer.consent:
                self.logger.info(f"[DISPATCHER-SKIP] Farmer {fid} skipped: consent not granted.")
                skipped_ineligible += 1
                if not self.ports.ledger.has_final_result(fid, call_date):
                    self.ports.ledger.record_day_result(
                        FarmerDayResult(fid, call_date, FinalResult.SKIPPED, 0, SkipReason.NO_CONSENT)
                    )
                continue

            if not farmer.phone:
                self.logger.info(f"[DISPATCHER-SKIP] Farmer {fid} skipped: no registered phone number.")
                skipped_ineligible += 1
                if not self.ports.ledger.has_final_result(fid, call_date):
                    self.ports.ledger.record_day_result(
                        FarmerDayResult(fid, call_date, FinalResult.SKIPPED, 0, SkipReason.NO_PHONE)
                    )
                continue

            total_eligible += 1

            # 4. Check duplicate dispatch
            if self.ports.ledger.has_daily_dispatch(fid, call_date) or self.ports.ledger.has_final_result(fid, call_date):
                self.logger.info(
                    f"[DISPATCHER-DUPLICATE] Farmer {fid} already has a dispatch record for {call_date.isoformat()}. Skipping."
                )
                skipped_duplicates += 1
                continue

            # 5. Create atomic initial dispatch record
            try:
                self.ports.ledger.create_daily_dispatch(
                    farmer_id=fid,
                    dispatch_date=call_date,
                    status=DispatchStatus.ACCEPTED.value,
                )
            except sqlite3.IntegrityError:
                self.logger.warning(
                    f"[DISPATCHER-DUPLICATE-RACE] DB constraint caught duplicate dispatch for farmer {fid}. Skipping."
                )
                skipped_duplicates += 1
                continue

            # 6 & 7. Place call and execute retry workflow
            try:
                farmer_outcome = self._dispatch_single_farmer(farmer, weather_report, call_date)
                submitted += 1
                if farmer_outcome.get("status") == "failed":
                    failed += 1
                details.append(farmer_outcome)
            except Exception as exc:
                self.logger.error(
                    f"[DISPATCHER-FARMER-ERROR] Failed to process call for farmer {fid}: {exc}",
                    exc_info=True,
                )
                failed += 1
                try:
                    self.ports.ledger.update_daily_dispatch(
                        farmer_id=fid,
                        dispatch_date=call_date,
                        status=DispatchStatus.FAILED.value,
                        error=type(exc).__name__,
                    )
                except Exception:
                    pass
                details.append({
                    "farmer_id": fid,
                    "status": "failed",
                    "error": str(exc),
                })
                # 9. Continue processing other farmers!
                continue

        end_dt = datetime.now(timezone.utc)
        duration_s = (end_dt - start_dt).total_seconds()
        final_status = "completed" if failed == 0 else "completed_with_failures"

        summary = DispatchSummary(
            dispatch_date=call_date,
            start_time=start_time_iso,
            end_time=end_dt.isoformat(),
            duration_s=duration_s,
            status=final_status,
            weather_fetched=True,
            total_eligible=total_eligible,
            submitted=submitted,
            failed=failed,
            skipped_duplicates=skipped_duplicates,
            skipped_ineligible=skipped_ineligible,
            details=details,
            weather_report=weather_report,
        )

        self.logger.info(
            f"[DISPATCHER-COMPLETE] Daily dispatch completed for {call_date.isoformat()} in {duration_s:.2f}s | "
            f"Status: {final_status} | Eligible: {total_eligible} | Submitted: {submitted} | "
            f"Failed: {failed} | Skipped Duplicates: {skipped_duplicates} | "
            f"Skipped Ineligible: {skipped_ineligible}"
        )
        return summary

    def _dispatch_single_farmer(
        self,
        farmer: FarmerContext,
        weather: WeatherReport,
        call_date: date,
    ) -> dict[str, Any]:
        """Dispatch call to an individual farmer with audio synthesis and retry management."""
        self.ports.ledger.update_daily_dispatch(
            farmer_id=farmer.farmer_id,
            dispatch_date=call_date,
            status=DispatchStatus.IN_PROGRESS.value,
        )

        message = build_message(farmer, weather)
        audio_ref = self.ports.voice.synthesize(message, farmer.language)

        last: ProviderCallResult | None = None
        attempts_used = 0

        for attempt_no in range(1, self.settings.max_attempts + 1):
            attempts_used = attempt_no
            try:
                self.logger.info(
                    f"[CALL-ATTEMPT] Dialing farmer {farmer.farmer_id} "
                    f"(Attempt {attempt_no}/{self.settings.max_attempts}, Language: {farmer.language.value})"
                )
                last = self.ports.telephony.place_call(farmer.phone, audio_ref)
            except Exception as exc:
                self.logger.warning(
                    f"[CALL-ATTEMPT-FAIL] Telephony provider exception for {farmer.farmer_id}: {type(exc).__name__}"
                )
                last = ProviderCallResult(AttemptStatus.FAILED, error=type(exc).__name__)

            # Record each attempt in ledger
            self.ports.ledger.record_attempt(CallAttempt(
                farmer_id=farmer.farmer_id,
                call_date=call_date,
                attempt_no=attempt_no,
                status=last.status,
                language=farmer.language,
                message_text=message,
                provider_call_id=last.provider_call_id,
                duration_s=last.duration_s,
                error=last.error,
                weather_source=weather.source,
            ))

            if last.status is AttemptStatus.ANSWERED:
                self.ports.ledger.update_daily_dispatch(
                    farmer_id=farmer.farmer_id,
                    dispatch_date=call_date,
                    status=DispatchStatus.COMPLETED.value,
                    provider_call_id=last.provider_call_id,
                )
                break

            if attempt_no < self.settings.max_attempts:
                # Retry scheduled
                self.logger.info(
                    f"[CALL-RETRY] Farmer {farmer.farmer_id} {last.status.value}. "
                    f"Scheduling retry {attempt_no + 1} after {self.settings.retry_gap_minutes}min."
                )
                self.ports.ledger.update_daily_dispatch(
                    farmer_id=farmer.farmer_id,
                    dispatch_date=call_date,
                    status=DispatchStatus.RETRY_SCHEDULED.value,
                    provider_call_id=last.provider_call_id,
                    error=last.error,
                )
                self.wait_fn(self.settings.retry_gap_minutes)
            else:
                # Max attempts exhausted
                disp_status = (
                    DispatchStatus.FAILED.value
                    if last.status is AttemptStatus.FAILED
                    else DispatchStatus.UNANSWERED.value
                )
                self.ports.ledger.update_daily_dispatch(
                    farmer_id=farmer.farmer_id,
                    dispatch_date=call_date,
                    status=disp_status,
                    provider_call_id=last.provider_call_id,
                    error=last.error,
                )

        assert last is not None
        if last.status is AttemptStatus.ANSWERED:
            final_res = FinalResult.ANSWERED
        elif last.status is AttemptStatus.FAILED:
            final_res = FinalResult.FAILED
        else:
            final_res = FinalResult.UNANSWERED

        self.ports.ledger.record_day_result(
            FarmerDayResult(farmer.farmer_id, call_date, final_res, attempts_used)
        )

        return {
            "farmer_id": farmer.farmer_id,
            "status": "completed" if final_res is FinalResult.ANSWERED else final_res.value,
            "attempts": attempts_used,
            "provider_call_id": last.provider_call_id,
            "error": last.error,
        }
