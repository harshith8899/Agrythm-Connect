"""Open-Meteo weather and place lookup. Free, no API key. https://open-meteo.com

- geocode() turns Village + District + State into coordinates. Names repeat across India (there is a Mandya in
  Haryana too), so a match must sit in the farmer's state and district; otherwise there is no match and no call.
- OpenMeteoWeather asks for the next 7 days at once (get_forecast) and returns the requested day, or None when any
  field is missing or implausible, so a farmer is only called when real weather is in hand. StoredWeather keeps all
  7 days, so a later outage can fall back on a saved forecast.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

from ..contracts import WeatherReport

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes in short spoken words
_WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "foggy", 48: "foggy",
        51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
        61: "light rain", 63: "rainy", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
        71: "light snow", 73: "snowy", 75: "heavy snow", 77: "snowy",
        80: "light showers", 81: "showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers",
        95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail"}


# Say who is asking. A hosting provider's shared address that arrives as a bare "Python-urllib" is the kind of client that
# public APIs throttle or block; a named one with a contact is treated as a normal, polite caller.
USER_AGENT = "AgrythmConnect/1.0 (daily weather calls for farmers; https://github.com/harshith8899/Agrythm-Connect)"
_client = urllib.request.build_opener()
_client.addheaders = [("User-Agent", USER_AGENT), ("Accept", "application/json")]
default_opener = _client.open

FORECAST_DAYS = 7
DAILY_FIELDS = ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                "wind_speed_10m_max,relative_humidity_2m_mean")


def _get(url: str, params: dict, opener=default_opener) -> dict:
    with opener(f"{url}?{urllib.parse.urlencode(params)}", timeout=20) as resp:
        return json.load(resp)


def _same(a: object, b: str) -> bool:
    norm = lambda s: "".join(ch for ch in str(s or "").lower() if ch.isalnum())  # noqa: E731
    return bool(b) and norm(a) == norm(b)


@dataclass(frozen=True)
class Place:
    latitude: float
    longitude: float
    matched: str        # e.g. "Mandya, Mandya, Karnataka (village)" for a human to check
    level: str          # village | district


def geocode(village: str, district: str, state: str, opener=default_opener) -> Place | None:
    """Village first; if the village is unknown, the district centre. None when nothing matches confidently."""
    for name, level in ((village, "village"), (district, "district")):
        if not name:
            continue
        results = _get(GEOCODE_URL, {"name": name, "count": 10, "language": "en", "format": "json",
                                     "countryCode": "IN"}, opener).get("results") or []
        in_state = [r for r in results if not state or _same(r.get("admin1"), state)]
        in_district = [r for r in in_state
                       if not district or any(_same(r.get(k), district) for k in ("admin2", "admin3", "name"))]
        # without a district to check, accept only a single match inside the state
        pick = in_district[0] if in_district else (in_state[0] if not district and len(in_state) == 1 else None)
        if pick:
            where = ", ".join(str(pick.get(k)) for k in ("name", "admin2", "admin1") if pick.get(k))
            return Place(float(pick["latitude"]), float(pick["longitude"]), f"{where} ({level})", level)
    return None


class OpenMeteoWeather:
    def __init__(self, opener=default_opener):
        self._open = opener

    def get_forecast(self, place_name: str, latitude: float, longitude: float, start: date) -> dict[date, WeatherReport]:
        """The next 7 days from `start`. Days with a missing or implausible field are left out."""
        if not latitude and not longitude:
            return {}                       # no coordinates: never guess a place by name alone
        daily = _get(FORECAST_URL, {
            "latitude": latitude, "longitude": longitude, "timezone": "Asia/Kolkata", "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=FORECAST_DAYS - 1)).isoformat(), "daily": DAILY_FIELDS,
            "wind_speed_unit": "kmh",
        }, self._open).get("daily") or {}
        out: dict[date, WeatherReport] = {}
        for n, day in enumerate(daily.get("time") or []):
            try:
                code, tmax, tmin = daily["weather_code"][n], daily["temperature_2m_max"][n], daily["temperature_2m_min"][n]
                rain, wind = daily["precipitation_probability_max"][n], daily["wind_speed_10m_max"][n]
                humidity = daily["relative_humidity_2m_mean"][n]
                if None in (code, tmax, tmin, rain, wind, humidity):
                    continue
                words = _WMO.get(int(code))
                if (words is None or not (-10 <= tmin <= tmax <= 55) or not (0 <= rain <= 100)
                        or not (0 <= wind <= 250) or not (0 <= humidity <= 100)):
                    continue
                out[date.fromisoformat(day)] = WeatherReport(place_name, words, round(tmin), round(tmax), round(rain),
                                                             "open-meteo", round(wind), round(humidity))
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return out

    def get_weather(self, place_name: str, latitude: float, longitude: float, call_date: date) -> WeatherReport | None:
        return self.get_forecast(place_name, latitude, longitude, call_date).get(call_date)
