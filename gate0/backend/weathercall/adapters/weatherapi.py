"""WeatherAPI.com weather and place lookup. Needs a free key (WEATHERAPI_KEY). https://www.weatherapi.com

Used instead of Open-Meteo on hosting, where Open-Meteo's free service throttles shared addresses (HTTP 429).
- The forecast is asked for only when a call is being made (see StoredWeather: one request per place and day, every
  later farmer of the same place and any retry reuse the saved day). Nothing polls this API: the System tab reads the
  saved forecasts and never asks WeatherAPI.
- The free plan gives 3 days at once; every returned day is saved, so a later outage can fall back on them.
- geocode() turns Village + District + State into coordinates once, when a farmer is added or imported.
- The key travels in the request only, never in a log, a message or an error text.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from datetime import date

from ..contracts import WeatherReport
from . import open_meteo as om
from .open_meteo import Place, _same, default_opener

FORECAST_URL = "https://api.weatherapi.com/v1/forecast.json"
SEARCH_URL = "https://api.weatherapi.com/v1/search.json"
FORECAST_DAYS = 3                       # what the free plan returns; a larger plan may be given more with WEATHERAPI_DAYS
LABEL = "WeatherAPI.com"


def api_key() -> str:
    return os.environ.get("WEATHERAPI_KEY", "").strip()


def _days() -> int:
    try:
        return max(1, min(14, int(os.environ.get("WEATHERAPI_DAYS", FORECAST_DAYS))))
    except ValueError:
        return FORECAST_DAYS


def _get(url: str, params: dict, opener=default_opener) -> object:
    with opener(f"{url}?{urllib.parse.urlencode({**params, 'key': api_key()})}", timeout=20) as resp:
        return json.load(resp)


def geocode(village: str, district: str, state: str, opener=default_opener) -> Place | None:
    """Village first, then the district centre. Falls back to Open-Meteo's lookup when there is no WeatherAPI key."""
    if not api_key():
        return om.geocode(village, district, state, opener)
    for name, level in ((village, "village"), (district, "district")):
        if not name:
            continue
        results = _get(SEARCH_URL, {"q": name}, opener) or []
        in_india = [r for r in results if _same(r.get("country"), "india")]
        in_state = [r for r in in_india if not state or _same(r.get("region"), state)]
        pick = next((r for r in in_state if _same(r.get("name"), name)), None) or (in_state[0] if len(in_state) == 1 else None)
        if pick:
            where = ", ".join(str(pick.get(k)) for k in ("name", "region") if pick.get(k))
            return Place(float(pick["lat"]), float(pick["lon"]), f"{where} ({level})", level)
    return None


class WeatherApiWeather:
    label = LABEL

    def __init__(self, opener=default_opener):
        self._open = opener

    @property
    def uses_key(self) -> bool:
        return bool(api_key())

    def get_forecast(self, place_name: str, latitude: float, longitude: float, start: date) -> dict[date, WeatherReport]:
        """The coming days from today. Days with a missing or implausible field are left out."""
        if not latitude and not longitude:
            return {}                       # no coordinates: never guess a place by name alone
        if not api_key():
            raise RuntimeError("WEATHERAPI_KEY is not set")
        data = _get(FORECAST_URL, {"q": f"{latitude},{longitude}", "days": _days(), "aqi": "no", "alerts": "no"}, self._open)
        out: dict[date, WeatherReport] = {}
        for entry in (data.get("forecast") or {}).get("forecastday") or []:
            try:
                d = entry["day"]
                tmax, tmin, wind = d["maxtemp_c"], d["mintemp_c"], d["maxwind_kph"]
                humidity, rain = d["avghumidity"], d["daily_chance_of_rain"]
                words = str((d.get("condition") or {}).get("text") or "").strip().lower()
                if None in (tmax, tmin, wind, humidity, rain) or not words:
                    continue
                if (not (-10 <= tmin <= tmax <= 55) or not (0 <= rain <= 100) or not (0 <= wind <= 250)
                        or not (0 <= humidity <= 100)):
                    continue
                out[date.fromisoformat(entry["date"])] = WeatherReport(place_name, words, round(tmin), round(tmax), round(rain),
                                                                       "weatherapi", round(wind), round(humidity))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def get_weather(self, place_name: str, latitude: float, longitude: float, call_date: date) -> WeatherReport | None:
        return self.get_forecast(place_name, latitude, longitude, call_date).get(call_date)


def make_weather(env=None):
    """WeatherAPI.com when its key is set (or GATE0_WEATHER=weatherapi), otherwise Open-Meteo."""
    e = env if env is not None else os.environ
    if e.get("GATE0_WEATHER", "") == "weatherapi" or api_key():
        return WeatherApiWeather()
    return om.OpenMeteoWeather()
