"""Tests for Open-Meteo weather adapter.

Verifies URL construction, contract compliance, coordinate guards,
WMO code mapping, payload boundary validation, and network error handling
without making real HTTP calls, plus live network cross-checks.
"""

import io
import json
import socket
from datetime import date
from unittest.mock import patch
from urllib.error import URLError

import pytest

from weathercall.adapters.open_meteo import OpenMeteoWeather


# Fixed test fixtures for deterministic verification
CALL_DATE = date(2026, 11, 5)
LATITUDE = 17.9104
LONGITUDE = 77.5199


def payload(
    *,
    code=2,
    temp_max=32.6,
    temp_min=21.4,
    rain_chance=20.4,
    forecast_date="2026-11-05",
):
    """Build a mock Open-Meteo daily forecast JSON payload."""
    return {
        "daily": {
            "time": [forecast_date],
            "weather_code": [code],
            "temperature_2m_max": [temp_max],
            "temperature_2m_min": [temp_min],
            "precipitation_probability_max": [rain_chance],
        }
    }


def mocked_response(data):
    """Wrap a dictionary payload into an in-memory byte stream for urlopen."""
    return io.BytesIO(json.dumps(data).encode("utf-8"))


def test_valid_response_returns_bidar_weather_report():
    """Verify standard response parsing, rounding, and query URL construction."""
    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        return_value=mocked_response(payload()),
    ) as urlopen:
        report = OpenMeteoWeather().get_weather(
            "Bidar", LATITUDE, LONGITUDE, CALL_DATE
        )

    # Validate parsed WeatherReport dataclass fields and integer rounding
    assert report is not None
    assert report.place_name == "Bidar"
    assert report.summary == "partly cloudy"
    assert report.temp_min_c == 21
    assert report.temp_max_c == 33
    assert report.rain_chance_pct == 20
    assert report.source == "open-meteo"

    # Verify query string parameters sent to Open-Meteo
    request = urlopen.call_args.args[0]
    assert request.full_url.startswith(
        "https://api.open-meteo.com/v1/forecast?"
    )
    assert "latitude=17.9104" in request.full_url
    assert "longitude=77.5199" in request.full_url
    assert "timezone=Asia%2FKolkata" in request.full_url
    assert "start_date=2026-11-05" in request.full_url
    assert "end_date=2026-11-11" in request.full_url
    assert (
        "daily=weather_code%2Ctemperature_2m_max%2Ctemperature_2m_min%2C"
        "precipitation_probability_max"
    ) in request.full_url


def test_zero_coordinates_return_none_without_network_call():
    """Ensure coordinates (0.0, 0.0) exit immediately without network requests."""
    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen"
    ) as urlopen:
        report = OpenMeteoWeather().get_weather(
            "Bidar", 0.0, 0.0, CALL_DATE
        )

    assert report is None
    urlopen.assert_not_called()


@pytest.mark.parametrize(
    ("code", "summary"),
    [
        (0, "clear sky"),
        (2, "partly cloudy"),
        (3, "overcast"),
        (63, "heavy rain"),
        (95, "thunderstorms"),
    ],
)
def test_wmo_weather_code_mapping(code, summary):
    """Ensure supported WMO weather codes convert to readable spoken summaries."""
    report = OpenMeteoWeather._report_from_payload(
        "Bidar", CALL_DATE, payload(code=code)
    )

    assert report is not None
    assert report.summary == summary


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_2m_max", 60),
        ("temperature_2m_min", -15),
        ("precipitation_probability_max", 105),
        ("precipitation_probability_max", -5),
    ],
)
def test_implausible_values_return_none(field, value):
    """Reject forecasts with temperatures outside [-10, 55] or rain outside [0, 100]."""
    data = payload(code=0)
    data["daily"][field][0] = value
    report = OpenMeteoWeather._report_from_payload(
        "Bidar", CALL_DATE, data
    )

    assert report is None


def test_inverted_temperatures_return_none():
    """Reject forecasts where temp_min exceeds temp_max."""
    report = OpenMeteoWeather._report_from_payload(
        "Bidar", CALL_DATE, payload(temp_min=40, temp_max=20)
    )

    assert report is None


@pytest.mark.parametrize(
    "invalid_payload",
    [
        # Multi-day array when exactly 1 day expected
        {
            "daily": {
                "time": ["2026-11-05", "2026-11-06"],
                "weather_code": [2],
                "temperature_2m_max": [32],
                "temperature_2m_min": [21],
                "precipitation_probability_max": [20],
            }
        },
        # Missing required key (precipitation_probability_max)
        {
            "daily": {
                "time": ["2026-11-05"],
                "weather_code": [2],
                "temperature_2m_max": [32],
                "temperature_2m_min": [21],
            }
        },
        # Mismatched forecast date
        payload(forecast_date="2026-11-06"),
        # Non-finite values
        payload(temp_max=float("nan")),
        payload(temp_min=float("inf")),
    ],
)
def test_malformed_payload_returns_none(invalid_payload):
    """Reject malformed payloads, non-finite values, and date mismatches."""
    report = OpenMeteoWeather._report_from_payload(
        "Bidar", CALL_DATE, invalid_payload
    )

    assert report is None


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        URLError("service unavailable"),
    ],
)
def test_network_errors_return_none(error, tmp_path):
    """Verify socket timeouts and network errors gracefully yield None when no cached forecast exists."""
    empty_db = str(tmp_path / "empty.db")
    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        side_effect=error,
    ):
        report = OpenMeteoWeather(db_path=empty_db).get_weather(
            "Bidar", LATITUDE, LONGITUDE, CALL_DATE
        )

    assert report is None


def test_invalid_json_returns_none(tmp_path):
    """Verify corrupted JSON responses gracefully yield None when no cached forecast exists."""
    empty_db = str(tmp_path / "empty.db")
    response = io.BytesIO(b"{not valid json")
    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        return_value=response,
    ):
        report = OpenMeteoWeather(db_path=empty_db).get_weather(
            "Bidar", LATITUDE, LONGITUDE, CALL_DATE
        )

    assert report is None


def test_user_agent_header_present():
    """Verify standard User-Agent header is set to avoid provider rate limiting."""
    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        return_value=mocked_response(payload()),
    ) as urlopen:
        OpenMeteoWeather().get_weather("Bidar", LATITUDE, LONGITUDE, CALL_DATE)

    request = urlopen.call_args.args[0]
    assert "User-agent" in request.headers or "User-Agent" in request.headers


def test_unknown_weather_code_returns_none():
    """Codes outside WMO mapping return None (no forecast, no call)."""
    report = OpenMeteoWeather._report_from_payload(
        "Bidar", CALL_DATE, payload(code=999)
    )
    assert report is None


def test_boolean_values_in_payload_rejected():
    """Booleans pass isinstance(val, int) in Python; ensure they are rejected."""
    bad_data = payload()
    bad_data["daily"]["temperature_2m_max"][0] = True
    report = OpenMeteoWeather._report_from_payload("Bidar", CALL_DATE, bad_data)
    assert report is None


def test_real_open_meteo_json_structure_compatibility():
    """Verify parser compatibility with the exact multi-field response returned by api.open-meteo.com."""
    real_api_response = {
        "latitude": 17.891035,
        "longitude": 77.50486,
        "generationtime_ms": 0.156,
        "utc_offset_seconds": 19800,
        "timezone": "Asia/Kolkata",
        "timezone_abbreviation": "GMT+5:30",
        "elevation": 673.0,
        "daily_units": {
            "time": "iso8601",
            "weather_code": "wmo code",
            "temperature_2m_max": "\u00b0C",
            "temperature_2m_min": "\u00b0C",
            "precipitation_probability_max": "%",
        },
        "daily": {
            "time": ["2026-11-05"],
            "weather_code": [3],
            "temperature_2m_max": [29.7],
            "temperature_2m_min": [21.5],
            "precipitation_probability_max": [2],
        },
    }
    report = OpenMeteoWeather._report_from_payload("Bidar", CALL_DATE, real_api_response)
    assert report is not None
    assert report.place_name == "Bidar"
    assert report.summary == "overcast"
    assert report.temp_min_c == 22
    assert report.temp_max_c == 30
    assert report.rain_chance_pct == 2
    assert report.source == "open-meteo"


def test_live_open_meteo_bidar_report():
    """Cross-check that the live Open-Meteo endpoint responds with valid data for today's forecast."""
    try:
        socket.create_connection(("api.open-meteo.com", 443), timeout=3)
    except OSError:
        pytest.skip("api.open-meteo.com is currently unreachable")

    today = date.today()
    report = OpenMeteoWeather().get_weather("Bidar", LATITUDE, LONGITUDE, today)
    assert report is not None
    assert report.place_name == "Bidar"
    assert isinstance(report.summary, str) and len(report.summary) > 0
    assert -10 <= report.temp_min_c <= 55
    assert -10 <= report.temp_max_c <= 55
    assert report.temp_min_c <= report.temp_max_c
    assert 0 <= report.rain_chance_pct <= 100
    assert report.source == "open-meteo"


def test_custom_weather_api_url_and_key_from_env(monkeypatch):
    """Ensure adapter respects WEATHER_API_URL and WEATHER_API_KEY from environment."""
    monkeypatch.setenv("WEATHER_API_URL", "https://custom-proxy.internal/v1/forecast")
    monkeypatch.setenv("WEATHER_API_KEY", "secret-test-key")

    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        return_value=mocked_response(payload()),
    ) as urlopen:
        OpenMeteoWeather().get_weather("Bidar", LATITUDE, LONGITUDE, CALL_DATE)

    request = urlopen.call_args.args[0]
    assert request.full_url.startswith("https://custom-proxy.internal/v1/forecast?")
    assert "apikey=secret-test-key" in request.full_url


def test_open_meteo_maintenance_fallback_uses_previous_day_cached_forecast(tmp_path):
    """If Open-Meteo goes under maintenance, adapter accesses previous day forecast stored in DB."""
    db_file = str(tmp_path / "test_weather.db")
    adapter = OpenMeteoWeather(db_path=db_file, forecast_days=7)

    day1 = date(2026, 11, 5)
    day2 = date(2026, 11, 6)

    # 1. On Day 1, Open-Meteo is healthy and returns multi-day forecasts (covering Day 1 & upcoming Day 2)
    multi_day_payload = {
        "daily": {
            "time": ["2026-11-05", "2026-11-06"],
            "weather_code": [2, 3],
            "temperature_2m_max": [32.0, 30.0],
            "temperature_2m_min": [21.0, 20.0],
            "precipitation_probability_max": [10, 45],
        }
    }

    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        return_value=mocked_response(multi_day_payload),
    ):
        day1_report = adapter.get_weather("Bidar", LATITUDE, LONGITUDE, day1)

    assert day1_report is not None
    assert day1_report.place_name == "Bidar"
    assert day1_report.temp_max_c == 32
    assert day1_report.source == "open-meteo"

    # 2. On Day 2, Open-Meteo goes under maintenance (HTTP 503 Service Unavailable / Timeout)
    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        side_effect=URLError("503 Service Unavailable (Maintenance)"),
    ):
        day2_report = adapter.get_weather("Bidar", LATITUDE, LONGITUDE, day2)

    # 3. Verify that Day 2 accessed the forecast stored in SQLite from Day 1's fetch!
    assert day2_report is not None
    assert day2_report.place_name == "Bidar"
    assert day2_report.summary == "overcast"
    assert day2_report.temp_min_c == 20
    assert day2_report.temp_max_c == 30
    assert day2_report.rain_chance_pct == 45
    assert day2_report.source == "open-meteo (cached)"


