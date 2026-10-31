"""The four contracts between Gate Zero and the rest of the platform (Trust AI in the final product).

These are the "wires". Their shape is fixed here; what sits behind them can change.
  1. CallRequest      - ask for one weather call to one farmer for one day
  2. FarmerContext    - approved, consented farmer data needed to place the call
  3. CallAttempt      - one write per dial attempt, plus the final result
  4. CallStatusView   - read-only operational view for the monitoring page
Keep this file free of provider names and database details.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Language(str, Enum):
    HI = "hi"
    EN = "en"
    KN = "kn"


class AttemptStatus(str, Enum):
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"   # rang, nobody picked up
    BUSY = "busy"
    FAILED = "failed"         # provider or network error


class FinalResult(str, Enum):
    ANSWERED = "answered"
    UNANSWERED = "unanswered"  # all attempts used, never picked up
    FAILED = "failed"          # last attempt ended in an error
    SKIPPED = "skipped"        # never dialled (see skip_reason)


class SkipReason(str, Enum):
    NO_CONSENT = "no_consent"
    INACTIVE = "inactive"
    ALREADY_CALLED = "already_called_today"
    NO_WEATHER = "weather_unavailable"
    NO_PHONE = "no_phone"


@dataclass(frozen=True)
class CallRequest:                      # contract 1
    farmer_id: str
    call_date: date
    requested_by: str = "scheduler"     # scheduler | operator | trust_ai
    request_id: str | None = None       # idempotency key from the caller, if any


@dataclass(frozen=True)
class FarmerContext:                    # contract 2
    farmer_id: str
    display_name: str
    language: Language
    place_name: str
    latitude: float
    longitude: float
    consent: bool
    active: bool = True
    phone: str = field(default="", repr=False)   # sensitive: never print or log


@dataclass(frozen=True)
class WeatherReport:
    place_name: str
    summary: str            # short plain words, e.g. "partly cloudy"
    temp_min_c: int
    temp_max_c: int
    rain_chance_pct: int
    source: str             # which provider produced it (kept for accuracy checks)
    wind_speed_kmh: float = 0.0
    humidity_pct: int = 0


@dataclass(frozen=True)
class ProviderCallResult:
    status: AttemptStatus
    provider_call_id: str = ""
    duration_s: int = 0
    error: str = ""


@dataclass(frozen=True)
class CallAttempt:                      # contract 3
    farmer_id: str
    call_date: date
    attempt_no: int
    status: AttemptStatus
    language: Language
    message_text: str
    provider_call_id: str = ""
    duration_s: int = 0
    error: str = ""
    weather_source: str = ""


@dataclass(frozen=True)
class FarmerDayResult:
    farmer_id: str
    call_date: date
    result: FinalResult
    attempts: int
    skip_reason: SkipReason | None = None


@dataclass(frozen=True)
class CallStatusView:                   # contract 4 (no phone numbers, ever)
    call_date: date
    total: int
    answered: int
    unanswered: int
    failed: int
    skipped: int
    rows: tuple[FarmerDayResult, ...] = ()
