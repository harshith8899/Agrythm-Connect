"""Tests for Open-Meteo weather adapter.

Verifies URL construction, contract compliance, coordinate guards,
WMO code mapping, payload boundary validation, and network error handling
without making real HTTP calls.
"""

import io
import json
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
    assert "end_date=2026-11-05" in request.full_url
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
def test_network_errors_return_none(error):
    """Verify socket timeouts and network errors gracefully yield None."""
    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        side_effect=error,
    ):
        report = OpenMeteoWeather().get_weather(
            "Bidar", LATITUDE, LONGITUDE, CALL_DATE
        )

    assert report is None


def test_invalid_json_returns_none():
    """Verify corrupted JSON responses gracefully yield None."""
    response = io.BytesIO(b"{not valid json")
    with patch(
        "weathercall.adapters.open_meteo.urllib.request.urlopen",
        return_value=response,
    ):
        report = OpenMeteoWeather().get_weather(
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