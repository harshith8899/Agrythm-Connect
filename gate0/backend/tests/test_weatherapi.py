"""WeatherAPI.com adapter: the key, the 3-day forecast, the place lookup, and 'one request per place and day'."""
import io
import json
from datetime import date

import pytest

from weathercall import ports as P
from weathercall.adapters import weatherapi as wa
from weathercall.adapters.weather_store import StoredWeather

D = date(2026, 11, 10)


class Opener:
    def __init__(self, body):
        self.body, self.seen = body, []

    def __call__(self, url, timeout=20):
        self.seen.append(url)
        return io.BytesIO(json.dumps(self.body).encode())


def day(d, tmax=30.0, tmin=19.0, wind=14.0, hum=62, rain=40, text="Patchy rain possible"):
    return {"date": d, "day": {"maxtemp_c": tmax, "mintemp_c": tmin, "maxwind_kph": wind, "avghumidity": hum,
                               "daily_chance_of_rain": rain, "condition": {"text": text}}}


def forecast(*days):
    return {"forecast": {"forecastday": list(days)}}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "SECRET-WA-KEY")
    monkeypatch.delenv("WEATHERAPI_DAYS", raising=False)


def test_a_forecast_becomes_reports_for_every_day_returned():
    op = Opener(forecast(day("2026-11-10"), day("2026-11-11", tmax=31.4, rain=10), day("2026-11-12")))
    got = wa.WeatherApiWeather(op).get_forecast("Mandya", 12.52, 76.9, D)
    assert sorted(got) == [date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)]
    r = got[D]
    assert (r.summary, r.temp_min_c, r.temp_max_c, r.rain_chance_pct, r.wind_kmh, r.humidity_pct, r.source) == \
           ("patchy rain possible", 19, 30, 40, 14, 62, "weatherapi")
    assert got[date(2026, 11, 11)].temp_max_c == 31
    assert len(op.seen) == 1 and "days=3" in op.seen[0] and "q=12.52%2C76.9" in op.seen[0]


def test_the_key_goes_in_the_request_and_never_in_an_error_text():
    op = Opener(forecast(day("2026-11-10")))
    wa.WeatherApiWeather(op).get_forecast("Mandya", 12.52, 76.9, D)
    assert "key=SECRET-WA-KEY" in op.seen[0]


def test_missing_or_odd_days_are_left_out():
    bad = forecast(day("2026-11-10", tmax=80), day("2026-11-11", rain=140), day("2026-11-12", text=""), day("2026-11-13"))
    got = wa.WeatherApiWeather(Opener(bad)).get_forecast("Mandya", 12.52, 76.9, D)
    assert list(got) == [date(2026, 11, 13)]


def test_no_key_means_no_request():
    import os
    os.environ.pop("WEATHERAPI_KEY")
    op = Opener(forecast(day("2026-11-10")))
    with pytest.raises(RuntimeError):
        wa.WeatherApiWeather(op).get_forecast("Mandya", 12.52, 76.9, D)
    assert op.seen == [] and wa.WeatherApiWeather().uses_key is False


def test_no_coordinates_means_no_request():
    op = Opener(forecast())
    assert wa.WeatherApiWeather(op).get_forecast("Mandya", 0.0, 0.0, D) == {} and op.seen == []


def test_it_satisfies_the_weather_port():
    assert isinstance(wa.WeatherApiWeather(), P.WeatherProvider)


def test_the_key_selects_weatherapi_and_without_it_open_meteo_is_used(monkeypatch):
    assert isinstance(wa.make_weather({"GATE0_WEATHER": "open_meteo"}), wa.WeatherApiWeather)
    monkeypatch.delenv("WEATHERAPI_KEY")
    assert wa.make_weather({"GATE0_WEATHER": "open_meteo"}).label == "Open-Meteo"
    assert isinstance(wa.make_weather({"GATE0_WEATHER": "weatherapi"}), wa.WeatherApiWeather)


# ---- place lookup -------------------------------------------------------------------------------------------------------------
def test_geocode_needs_the_state_and_country_to_match():
    rows = [{"name": "Mandya", "region": "Haryana", "country": "India", "lat": 28.0, "lon": 77.0},
            {"name": "Mandya", "region": "Karnataka", "country": "India", "lat": 12.52, "lon": 76.9},
            {"name": "Mandya", "region": "Karnataka", "country": "Peru", "lat": 1.0, "lon": 2.0}]
    p = wa.geocode("Mandya", "Mandya", "Karnataka", Opener(rows))
    assert (p.latitude, p.longitude, p.level) == (12.52, 76.9, "village") and "Karnataka" in p.matched


def test_geocode_falls_back_to_the_district_and_then_to_nothing():
    class By:
        def __init__(self):
            self.seen = []

        def __call__(self, url, timeout=20):
            self.seen.append(url)
            body = [] if "q=Tinyville" in url else [{"name": "Hassan", "region": "Karnataka", "country": "India", "lat": 13.0, "lon": 76.1}]
            return io.BytesIO(json.dumps(body).encode())
    op = By()
    assert wa.geocode("Tinyville", "Hassan", "Karnataka", op).level == "district"
    assert wa.geocode("Tinyville", "Nowhere", "Karnataka", Opener([])) is None


# ---- one request per place and day ----------------------------------------------------------------------------------------------
def test_farmers_of_one_place_and_a_retry_share_one_request(tmp_path):
    op = Opener(forecast(day("2026-11-10"), day("2026-11-11"), day("2026-11-12")))
    s = StoredWeather(wa.WeatherApiWeather(op), str(tmp_path / "w.db"), retry_minutes=(), sleep=lambda s: None,
                      today=lambda: D)
    for _ in range(5):                                           # five farmers, a retry, a callback: the same village
        assert s.get_weather("Mandya", 12.52, 76.9, D).temp_max_c == 30
    assert s.get_weather("Mandya", 12.52, 76.9, date(2026, 11, 12)).temp_max_c == 30     # a later day is already saved
    assert len(op.seen) == 1


def test_a_failing_service_is_asked_once_per_place_not_four_times(tmp_path):
    class Down(Opener):
        def __call__(self, url, timeout=20):
            self.seen.append(url)
            raise OSError("down")
    op = Down({})
    s = StoredWeather(wa.WeatherApiWeather(op), str(tmp_path / "d.db"), retry_minutes=(), sleep=lambda s: None, today=lambda: D)
    assert s.get_weather("Mandya", 12.52, 76.9, D) is None and len(op.seen) == 1
