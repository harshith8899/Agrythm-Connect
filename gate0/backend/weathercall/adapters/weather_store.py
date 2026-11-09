"""Stores weather in SQLite before it is used, so the call says exactly what was fetched and saved.

Wraps any WeatherProvider. Order of events for one farmer's place and day:
 1. A report fetched TODAY is reused (no second fetch, and every farmer in one village hears the same numbers).
 2. Otherwise the provider is asked for its 7-day forecast and every day is saved.
 3. If the provider fails or has no complete weather, the fetch is retried after each wait in `retry_minutes`
    (client rule: +15 min, then +30 more, then +60 more = 15, 45 and 105 minutes after the first failure).
 4. If it still fails, the forecast saved on an earlier day for that date is used (source ends in "-saved"),
    because the 7-day forecast already covers it. With nothing saved either, there is no weather and the farmer
    is skipped.
After one place has used up its waits, other places in the same run try once and then use saved forecasts, so
an outage delays the run once, not once per village. A provider error is never raised.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime

from ..contracts import WeatherReport
from ..db import connect, table_columns

_SCHEMA = """
CREATE TABLE IF NOT EXISTS weather(
  place_key TEXT, lat REAL, lon REAL, call_date TEXT, place_name TEXT, summary TEXT, temp_min_c INT, temp_max_c INT,
  rain_chance_pct INT, source TEXT, fetched_at TEXT, wind_kmh INT, humidity_pct INT,
  PRIMARY KEY(place_key, lat, lon, call_date));
"""
_COLS = "summary, temp_min_c, temp_max_c, rain_chance_pct, source, wind_kmh, humidity_pct, fetched_at"
DEFAULT_RETRY_MINUTES = (15, 30, 60)


class StoredWeather:
    def __init__(self, inner, path: str = ":memory:", retry_minutes: tuple[int, ...] = DEFAULT_RETRY_MINUTES,
                 sleep=time.sleep, today=date.today):
        self.inner = inner
        self.retry_minutes = tuple(retry_minutes)
        self._sleep, self._today = sleep, today
        self.db = connect(path)
        self.db.executescript(_SCHEMA)
        have = table_columns(self.db, "weather")
        for col in ("wind_kmh", "humidity_pct"):          # older files: those rows stay unusable (NULL) as fallback
            if col not in have:
                self.db.execute(f"ALTER TABLE weather ADD COLUMN {col} INT")
        self.db.commit()
        self.provider_errors = 0
        self.fallbacks = 0
        self._gave_up = False

    # -- reading and writing saved days -------------------------------------------------------------------------
    def _saved(self, key: tuple, place_name: str) -> tuple[WeatherReport, str] | None:
        row = self.db.execute(f"SELECT {_COLS} FROM weather WHERE place_key=? AND lat=? AND lon=? AND call_date=? "
                              "AND wind_kmh IS NOT NULL AND humidity_pct IS NOT NULL", key).fetchone()
        if not row:
            return None
        return WeatherReport(place_name, row[0], row[1], row[2], row[3], row[4], row[5], row[6]), row[7][:10]

    def _save(self, pkey: tuple, place_name: str, forecast: dict[date, WeatherReport]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        rows = [(*pkey, d.isoformat(), place_name, r.summary, r.temp_min_c, r.temp_max_c, r.rain_chance_pct, r.source,
                 now, r.wind_kmh, r.humidity_pct) for d, r in forecast.items()]
        self.db.executemany("INSERT OR REPLACE INTO weather VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        self.db.commit()

    # -- asking the provider ------------------------------------------------------------------------------------
    def _fetch(self, place_name: str, lat: float, lon: float, call_date: date) -> dict[date, WeatherReport]:
        try:
            if hasattr(self.inner, "get_forecast"):
                return self.inner.get_forecast(place_name, lat, lon, call_date)
            one = self.inner.get_weather(place_name, lat, lon, call_date)
            return {call_date: one} if one is not None else {}
        except Exception:
            self.provider_errors += 1
            return {}

    def get_weather(self, place_name: str, latitude: float, longitude: float, call_date: date) -> WeatherReport | None:
        pkey = (place_name.strip().lower(), round(latitude, 3), round(longitude, 3))
        key = (*pkey, call_date.isoformat())
        saved = self._saved(key, place_name)
        if saved and saved[1] == self._today().isoformat():
            return saved[0]                                   # fetched today: use as is

        waits = [0] if self._gave_up else [0, *self.retry_minutes]
        for wait in waits:
            if wait:
                self._sleep(wait * 60)
            forecast = self._fetch(place_name, latitude, longitude, call_date)
            if call_date in forecast:
                self._save(pkey, place_name, forecast)
                return forecast[call_date]
        self._gave_up = True

        if saved:                                             # an earlier day's forecast covers this date
            self.fallbacks += 1
            r = saved[0]
            return WeatherReport(r.place_name, r.summary, r.temp_min_c, r.temp_max_c, r.rain_chance_pct,
                                 f"{r.source}-saved", r.wind_kmh, r.humidity_pct)
        return None
