"""Offline mock providers for development and tests. No network, no keys, no real people."""
from __future__ import annotations

from datetime import date

from ..contracts import AttemptStatus, Language, ProviderCallResult, WeatherReport


class MockWeather:
    def __init__(self, data: dict[str, WeatherReport] | None = None):
        self.data = data if data is not None else DEMO_WEATHER

    def get_weather(self, place_name: str, latitude: float, longitude: float, call_date: date) -> WeatherReport | None:
        return self.data.get(place_name)


class MockVoice:
    def synthesize(self, text: str, language: Language) -> str:
        return f"mock-audio:{language.value}:{len(text)}"


class MockTelephony:
    """script maps a phone to the outcomes of successive attempts; the last one repeats. Default: answered."""
    def __init__(self, script: dict[str, list[AttemptStatus]] | None = None):
        self.script = script or {}
        self._count: dict[str, int] = {}

    def place_call(self, phone: str, audio_ref: str) -> ProviderCallResult:
        i = self._count.get(phone, 0)
        self._count[phone] = i + 1
        outcomes = self.script.get(phone, [AttemptStatus.ANSWERED])
        status = outcomes[min(i, len(outcomes) - 1)]
        ok = status is AttemptStatus.ANSWERED
        return ProviderCallResult(
            status=status, provider_call_id=f"mock-{abs(hash(phone)) % 10**6}-{i + 1}",
            duration_s=35 if ok else 0, error="" if status is not AttemptStatus.FAILED else "mock_failure",
        )


DEMO_WEATHER = {
    "Mandya": WeatherReport("Mandya", "partly cloudy", 21, 32, 20, "mock", wind_speed_kmh=12.0, humidity_pct=65),
    "Hassan": WeatherReport("Hassan", "light rain", 19, 27, 70, "mock", wind_speed_kmh=15.5, humidity_pct=80),
    "Mysuru": WeatherReport("Mysuru", "clear", 20, 33, 5, "mock", wind_speed_kmh=8.0, humidity_pct=50),
    # "Nowhere" is intentionally absent: exercises the weather-missing path
}
