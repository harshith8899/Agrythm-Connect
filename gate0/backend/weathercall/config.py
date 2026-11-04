"""Settings from environment. Defaults are placeholders until confirmed with the client."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_attempts: int = 3               # UNCONFIRMED with client
    retry_gap_minutes: int = 30         # UNCONFIRMED with client
    call_time: str = "09:00"            # team trial choice (26 Oct 2026); UNCONFIRMED with client
    on_weather_missing: str = "skip"    # skip | (other behaviours to be agreed)
    target_seconds_min: int = 30
    target_seconds_max: int = 40

    @classmethod
    def from_env(cls) -> "Settings":
        g = os.environ.get
        return cls(
            max_attempts=int(g("GATE0_MAX_ATTEMPTS", cls.max_attempts)),
            retry_gap_minutes=int(g("GATE0_RETRY_GAP_MINUTES", cls.retry_gap_minutes)),
            call_time=g("GATE0_CALL_TIME", cls.call_time),
            on_weather_missing=g("GATE0_ON_WEATHER_MISSING", cls.on_weather_missing),
        )
