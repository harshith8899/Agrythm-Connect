"""Open-Meteo weather adapter.

This adapter implements the WeatherProvider port interface defined in
`weathercall.ports`. It queries the Open-Meteo forecast API for daily weather
metrics (WMO weather code, high/low temperatures, and maximum precipitation
probability), validates the results against physical plausibility bounds,
and constructs a domain `WeatherReport`.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from ..contracts import WeatherReport


# Open-Meteo free forecast API configuration
_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEZONE = "Asia/Kolkata"
_DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,"
    "precipitation_probability_max"
)


def _summary_for_code(code: int) -> str | None:
    """Map standard WMO weather interpretation codes to spoken descriptions.

    Converts numerical weather codes (0-99) into clear, concise phrases
    suitable for text-to-speech voice generation. Returns None for unrecognized codes.
    """
    if code == 0:
        return "clear sky"
    if code in (1, 2):
        return "partly cloudy"
    if code == 3:
        return "overcast"
    if code in (45, 48):
        return "foggy"
    if 51 <= code <= 57:
        return "light rain"
    if 61 <= code <= 65:
        return "heavy rain" if code >= 63 else "light rain"
    if code in (66, 67):
        return "freezing rain"
    if 71 <= code <= 77:
        return "snow"
    if 80 <= code <= 82:
        return "rain showers"
    if code in (85, 86):
        return "snow showers"
    if 95 <= code <= 99:
        return "thunderstorms"
    return None


def _finite_number(value: Any) -> bool:
    """Validate that a value is a real, finite number (int or float).

    Explicitly excludes booleans (which inherit from int in Python) as well as
    NaN and infinite values that could bypass numerical boundary checks.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class OpenMeteoWeather:
    """Adapter to fetch and parse daily weather forecasts from Open-Meteo.

    Fulfills the `WeatherProvider` protocol from `weathercall.ports`.
    """

    def get_weather(
        self,
        place_name: str,
        latitude: float,
        longitude: float,
        call_date: date,
    ) -> WeatherReport | None:
        """Fetch daily weather for a given place, coordinates, and date.

        Args:
            place_name: Display name of the locality/village.
            latitude: Geographic latitude in decimal degrees.
            longitude: Geographic longitude in decimal degrees.
            call_date: Target date for the daily weather forecast.

        Returns:
            A validated `WeatherReport` instance if the fetch and payload
            validation succeed, or None if coordinates are missing, network
            requests fail, or payload values are implausible/corrupt.
        """
        # Guard clause: (0.0, 0.0) indicates missing or unmapped coordinates
        if latitude == 0.0 and longitude == 0.0:
            return None

        # Build query parameters targeting a single date window
        query = urllib.parse.urlencode({
            "latitude": latitude,
            "longitude": longitude,
            "daily": _DAILY_FIELDS,
            "timezone": _TIMEZONE,
            "start_date": call_date.isoformat(),
            "end_date": call_date.isoformat(),
        })

        # Request includes a custom User-Agent to comply with Open-Meteo usage policy
        request = urllib.request.Request(
            f"{_BASE_URL}?{query}",
            headers={"User-Agent": "Agrythm-Connect-Gate0/1.0"},
            method="GET",
        )

        try:
            # 10-second timeout ensures morning batch runs are not stalled by network lags
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            # Network outages or malformed HTTP responses result in None (caller will skip)
            return None

        return self._report_from_payload(place_name, call_date, payload)

    @staticmethod
    def _report_from_payload(
        place_name: str, call_date: date, payload: Any
    ) -> WeatherReport | None:
        """Validate and map raw API JSON response into a WeatherReport dataclass.

        Args:
            place_name: Locality name to attach to the report.
            call_date: Expected forecast date.
            payload: Decoded JSON dictionary from Open-Meteo.

        Returns:
            A populated `WeatherReport` if all integrity and boundary checks pass;
            otherwise None.
        """
        if not isinstance(payload, dict):
            return None

        daily = payload.get("daily")
        if not isinstance(daily, dict):
            return None

        # Ensure all expected forecast attributes are present as lists
        required = (
            "time",
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
        )
        if any(not isinstance(daily.get(field), list) for field in required):
            return None

        # Ensure single-day query returns exactly one data point per metric
        if any(len(daily[field]) != 1 for field in required):
            return None

        # Ensure returned data matches the requested date
        if daily["time"][0] != call_date.isoformat():
            return None

        code = daily["weather_code"][0]
        temp_max = daily["temperature_2m_max"][0]
        temp_min = daily["temperature_2m_min"][0]
        rain_chance = daily["precipitation_probability_max"][0]

        # Rigorous sanity checks:
        # 1. Weather code must be a finite integer.
        # 2. Temperatures and rain chance must be finite numbers.
        # 3. Temperatures must stay within realistic terrestrial limits (-10°C to 55°C).
        # 4. Rain chance probability must be between 0% and 100%.
        # 5. Minimum temperature cannot exceed maximum temperature.
        if (
            not _finite_number(code)
            or int(code) != code
            or not _finite_number(temp_min)
            or not _finite_number(temp_max)
            or not _finite_number(rain_chance)
            or not -10 <= temp_min <= 55
            or not -10 <= temp_max <= 55
            or not 0 <= rain_chance <= 100
            or temp_min > temp_max
        ):
            return None

        summary = _summary_for_code(int(code))
        if summary is None:
            return None

        # Construct domain contract with rounded integer values for speech clarity
        return WeatherReport(
            place_name=place_name,
            summary=summary,
            temp_min_c=round(temp_min),
            temp_max_c=round(temp_max),
            rain_chance_pct=round(rain_chance),
            source="open-meteo",
        )