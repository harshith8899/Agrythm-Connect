"""Open-Meteo weather adapter with database-backed forecast caching and maintenance fallback.

This adapter implements the WeatherProvider port interface defined in
`weathercall.ports`. It queries the Open-Meteo forecast API for daily weather
metrics (WMO weather code, high/low temperatures, and maximum precipitation
probability) for current and upcoming days, validates the results, and stores
the forecasts in SQLite.

If Open-Meteo goes under maintenance or encounters a network outage, the adapter
automatically accesses upcoming day forecasts stored during previous days' runs.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..contracts import WeatherReport


# Open-Meteo forecast API configuration
_DEFAULT_BASE_URL = "https://api.open-meteo.com/v1/forecast"
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
    """Adapter to fetch and parse daily weather forecasts from Open-Meteo with local DB fallback.

    Fulfills the `WeatherProvider` protocol from `weathercall.ports`.
    If the network or Open-Meteo API is down (maintenance), falls back to
    previously stored forecasts for the requested date.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        db_path: str | None = None,
        forecast_days: int | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("WEATHER_API_URL")
            or os.environ.get("OPEN_METEO_URL")
            or _DEFAULT_BASE_URL
        )
        self.api_key = (
            api_key
            or os.environ.get("WEATHER_API_KEY")
            or os.environ.get("OPEN_METEO_API_KEY")
            or None
        )
        self.db_path = (
            db_path
            or os.environ.get("GATE0_DB")
            or os.environ.get("WEATHER_DB_PATH")
            or None
        )
        if forecast_days is not None:
            self.forecast_days = forecast_days
        else:
            self.forecast_days = int(os.environ.get("WEATHER_FORECAST_DAYS", "7"))

    def _resolve_db_path(self) -> str | None:
        if self.db_path:
            return self.db_path
        env_db = os.environ.get("GATE0_DB") or os.environ.get("WEATHER_DB_PATH")
        if env_db:
            return env_db
        candidates = [
            pathlib.Path.cwd() / "weathercall.db",
            pathlib.Path(__file__).resolve().parent.parent / "weathercall.db",
            pathlib.Path(__file__).resolve().parent.parent.parent / "weathercall.db",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        return str(pathlib.Path(__file__).resolve().parent.parent / "weathercall.db")

    @staticmethod
    def _ensure_db_schema(conn: sqlite3.Connection) -> None:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS weather(
          place_name TEXT, lat REAL, lon REAL, forecast_date TEXT, summary TEXT, temp_min_c INT, temp_max_c INT,
          rain_chance_pct INT, source TEXT, fetched_at TEXT,
          PRIMARY KEY(place_name, forecast_date, fetched_at));
        CREATE INDEX IF NOT EXISTS idx_weather_lookup ON weather(place_name, forecast_date);
        """)

    def _store_reports_in_db(
        self,
        place_name: str,
        lat: float,
        lon: float,
        reports_by_date: dict[str, WeatherReport],
        fetched_at: str | None = None,
    ) -> None:
        db_path = self._resolve_db_path()
        if not db_path:
            return
        ts = fetched_at or datetime.now(timezone.utc).isoformat()
        try:
            with sqlite3.connect(db_path) as conn:
                self._ensure_db_schema(conn)
                for fdate, rep in reports_by_date.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO weather VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            place_name,
                            lat,
                            lon,
                            fdate,
                            rep.summary,
                            rep.temp_min_c,
                            rep.temp_max_c,
                            rep.rain_chance_pct,
                            rep.source,
                            ts,
                        ),
                    )
                conn.commit()
        except Exception:
            pass

    def _get_cached_forecast(self, place_name: str, call_date: date) -> WeatherReport | None:
        db_path = self._resolve_db_path()
        if not db_path:
            return None
        fdate = call_date.isoformat()
        try:
            with sqlite3.connect(db_path) as conn:
                self._ensure_db_schema(conn)
                row = conn.execute(
                    "SELECT place_name, summary, temp_min_c, temp_max_c, rain_chance_pct, source, fetched_at "
                    "FROM weather WHERE place_name=? AND forecast_date=? ORDER BY fetched_at DESC LIMIT 1",
                    (place_name, fdate),
                ).fetchone()
                if row:
                    src = row[5]
                    if not src.endswith("(cached)"):
                        src = f"{src} (cached)"
                    return WeatherReport(
                        place_name=row[0],
                        summary=row[1],
                        temp_min_c=row[2],
                        temp_max_c=row[3],
                        rain_chance_pct=row[4],
                        source=src,
                    )
        except Exception:
            return None
        return None

    def get_weather(
        self,
        place_name: str,
        latitude: float,
        longitude: float,
        call_date: date,
    ) -> WeatherReport | None:
        """Fetch daily weather for a given place, coordinates, and date.

        If Open-Meteo is unreachable (e.g. under maintenance), accesses
        stored upcoming forecast records from the local SQLite database.
        """
        # Guard clause: (0.0, 0.0) indicates missing or unmapped coordinates
        if latitude == 0.0 and longitude == 0.0:
            return None

        # Build query parameters targeting call_date up to forecast_days window
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": _DAILY_FIELDS,
            "timezone": _TIMEZONE,
            "start_date": call_date.isoformat(),
        }
        if self.forecast_days > 1:
            params["end_date"] = (call_date + timedelta(days=self.forecast_days - 1)).isoformat()
        else:
            params["end_date"] = call_date.isoformat()

        if self.api_key:
            params["apikey"] = self.api_key

        query = urllib.parse.urlencode(params)

        request = urllib.request.Request(
            f"{self.base_url}?{query}",
            headers={"User-Agent": "Agrythm-Connect-Gate0/1.0"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            # API failure or provider maintenance: fallback to cached forecast stored in DB
            return self._get_cached_forecast(place_name, call_date)

        # Parse all available forecast dates from response
        reports_by_date = self._reports_from_payload(place_name, payload)
        if not reports_by_date:
            return self._get_cached_forecast(place_name, call_date)

        # Persist current & upcoming forecasts to SQLite DB for maintenance resilience
        self._store_reports_in_db(place_name, latitude, longitude, reports_by_date)

        # Return the report for the requested call_date if present
        target_report = reports_by_date.get(call_date.isoformat())
        if target_report is not None:
            return target_report

        return self._get_cached_forecast(place_name, call_date)

    @staticmethod
    def _reports_from_payload(
        place_name: str, payload: Any
    ) -> dict[str, WeatherReport]:
        """Validate and map API JSON response into a dictionary of {date_str: WeatherReport}."""
        if not isinstance(payload, dict):
            return {}

        daily = payload.get("daily")
        if not isinstance(daily, dict):
            return {}

        required = (
            "time",
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
        )
        if any(not isinstance(daily.get(field), list) for field in required):
            return {}

        count = len(daily["time"])
        if count == 0 or any(len(daily[field]) != count for field in required):
            return {}

        results: dict[str, WeatherReport] = {}
        for i in range(count):
            fdate_str = str(daily["time"][i])
            code = daily["weather_code"][i]
            temp_max = daily["temperature_2m_max"][i]
            temp_min = daily["temperature_2m_min"][i]
            rain_chance = daily["precipitation_probability_max"][i]

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
                continue

            summary = _summary_for_code(int(code))
            if summary is None:
                continue

            results[fdate_str] = WeatherReport(
                place_name=place_name,
                summary=summary,
                temp_min_c=round(temp_min),
                temp_max_c=round(temp_max),
                rain_chance_pct=round(rain_chance),
                source="open-meteo",
            )
        return results

    @classmethod
    def _report_from_payload(
        cls, place_name: str, call_date: date, payload: Any
    ) -> WeatherReport | None:
        """Validate and map API JSON response into a single WeatherReport for call_date."""
        reports = cls._reports_from_payload(place_name, payload)
        return reports.get(call_date.isoformat())
