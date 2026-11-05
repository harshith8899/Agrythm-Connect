"""The call engine. Depends only on contracts and ports, never on a concrete provider or database."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from .config import Settings
from .contracts import (
    AttemptStatus, CallAttempt, CallRequest, CallStatusView, FarmerContext, FarmerDayResult,
    FinalResult, ProviderCallResult, SkipReason, WeatherReport,
)
from .ports import CallLedger, FarmerSource, TelephonyProvider, VoiceProvider, WeatherProvider
from .script import build_message


@dataclass
class Ports:
    farmers: FarmerSource
    ledger: CallLedger
    weather: WeatherProvider
    voice: VoiceProvider
    telephony: TelephonyProvider


def _skip(req: CallRequest, reason: SkipReason, ports: Ports) -> FarmerDayResult:
    r = FarmerDayResult(req.farmer_id, req.call_date, FinalResult.SKIPPED, 0, reason)
    ports.ledger.record_day_result(r)
    return r


@dataclass(frozen=True)
class PreparedCall:
    """A farmer who passed every check, with the weather and the exact words to speak."""
    farmer: FarmerContext
    weather: WeatherReport
    message: str


def prepare_call(req: CallRequest, ports: Ports, settings: Settings) -> PreparedCall | FarmerDayResult:
    """All checks before a phone may ring. Returns the call to make, or the recorded skip.
    Shared by direct dialling (process_request) and Sarvam campaigns (campaign.py)."""
    if ports.ledger.has_final_result(req.farmer_id, req.call_date):
        return FarmerDayResult(req.farmer_id, req.call_date, FinalResult.SKIPPED, 0, SkipReason.ALREADY_CALLED)

    farmer = ports.farmers.get_context(req.farmer_id)
    if farmer is None or not farmer.active:
        return _skip(req, SkipReason.INACTIVE, ports)
    if not farmer.consent:
        return _skip(req, SkipReason.NO_CONSENT, ports)
    if not farmer.phone:
        return _skip(req, SkipReason.NO_PHONE, ports)

    if settings.on_weather_missing != "skip":
        raise ValueError("Only on_weather_missing='skip' is implemented until the client confirms another behaviour")
    weather = ports.weather.get_weather(farmer.place_name, farmer.latitude, farmer.longitude, req.call_date)
    if weather is None:
        return _skip(req, SkipReason.NO_WEATHER, ports)
    return PreparedCall(farmer, weather, build_message(farmer, weather))


def final_result(last: AttemptStatus) -> FinalResult:
    """The day's result from the last attempt's status."""
    if last is AttemptStatus.ANSWERED:
        return FinalResult.ANSWERED
    if last is AttemptStatus.FAILED:
        return FinalResult.FAILED
    return FinalResult.UNANSWERED


def process_request(req: CallRequest, ports: Ports, settings: Settings,
                    wait: Callable[[int], None] = lambda minutes: None) -> FarmerDayResult:
    """Handle contract 1: one weather call to one farmer for one day. Safe to call twice (idempotent)."""
    prepared = prepare_call(req, ports, settings)
    if isinstance(prepared, FarmerDayResult):
        return prepared
    farmer, weather, message = prepared.farmer, prepared.weather, prepared.message
    try:
        audio_ref = ports.voice.synthesize(message, farmer.language)
    except Exception:  # a voice outage fails this farmer for today, never the whole morning run
        result = FarmerDayResult(farmer.farmer_id, req.call_date, FinalResult.FAILED, 0)
        ports.ledger.record_day_result(result)
        return result

    last: ProviderCallResult | None = None
    for n in range(1, settings.max_attempts + 1):
        try:
            last = ports.telephony.place_call(farmer.phone, audio_ref)
        except Exception as exc:  # provider errors must never stop the morning run; keep type only, no details
            last = ProviderCallResult(AttemptStatus.FAILED, error=type(exc).__name__)
        ports.ledger.record_attempt(CallAttempt(
            farmer_id=farmer.farmer_id, call_date=req.call_date, attempt_no=n, status=last.status,
            language=farmer.language, message_text=message, provider_call_id=last.provider_call_id,
            duration_s=last.duration_s, error=last.error, weather_source=weather.source,
        ))
        if last.status is AttemptStatus.ANSWERED:
            break
        if n < settings.max_attempts:
            wait(settings.retry_gap_minutes)

    assert last is not None
    result = FarmerDayResult(farmer.farmer_id, req.call_date, final_result(last.status), n)
    ports.ledger.record_day_result(result)
    return result


def run_morning(call_date: date, ports: Ports, settings: Settings,
                wait: Callable[[int], None] = lambda minutes: None) -> CallStatusView:
    """Standalone trigger: ask the farmer source who is callable today and handle each request."""
    for fid in ports.farmers.list_callable_ids(call_date):
        process_request(CallRequest(fid, call_date), ports, settings, wait)
    return ports.ledger.status(call_date)
