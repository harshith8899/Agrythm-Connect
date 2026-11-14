"""Places typed the way people write them: old spellings and misspellings still find the place, and a farmer saved without
a location is looked up again on the next save."""
import io
import json
import urllib.parse

import pytest

from weathercall import service as service_module
from weathercall.adapters import open_meteo as om
from weathercall.adapters import weatherapi as wa
from weathercall.adapters.dialers import MockDialler
from weathercall.adapters.open_meteo import Place, name_variants
from weathercall.service import DashboardService


@pytest.mark.parametrize("typed, expected", [
    ("banglore", ["banglore", "Bengaluru"]), ("Bangalore", ["Bangalore", "Bengaluru"]), ("Mysore", ["Mysore", "Mysuru"]),
    ("Mandya", ["Mandya"]), ("Bengaluru", ["Bengaluru"]), ("", [""]),
])
def test_name_variants_add_the_name_the_services_know(typed, expected):
    assert name_variants(typed) == expected


def test_open_meteo_finds_a_misspelled_district_by_its_known_name():
    seen = []

    def opener(url, timeout):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["name"][0]
        seen.append(q)
        rows = [{"name": "Bengaluru", "latitude": 12.97, "longitude": 77.59, "admin1": "Karnataka", "admin2": "Bengaluru Urban"}] \
            if q == "Bengaluru" else []
        return io.BytesIO(json.dumps({"results": rows}).encode())
    p = om.geocode("Rajajinagar", "Banglore", "Karnataka", opener)
    assert p is not None and p.level == "district" and (p.latitude, p.longitude) == (12.97, 77.59)
    assert "Banglore" in seen and "Bengaluru" in seen                          # what was typed first, then the known name


def test_weatherapi_finds_a_misspelled_district_by_its_known_name(monkeypatch):
    monkeypatch.setenv("WEATHERAPI_KEY", "k")
    seen = []

    def opener(url, timeout):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
        seen.append(q)
        rows = [{"name": "Bengaluru", "region": "Karnataka", "country": "India", "lat": 12.97, "lon": 77.59}] if q == "Bengaluru" else []
        return io.BytesIO(json.dumps(rows).encode())
    p = wa.geocode("Rajajinagar", "banglore", "Karnataka", opener)
    assert p is not None and p.level == "district" and (p.latitude, p.longitude) == (12.97, 77.59)
    assert seen[-2:] == ["banglore", "Bengaluru"]


def make(tmp_path):
    return DashboardService(str(tmp_path / "p.db"), dialler=MockDialler(), env={"GATE0_WEATHER": "open_meteo"})


def test_a_farmer_saved_without_a_location_is_looked_up_again_on_the_next_save(tmp_path, monkeypatch):
    s = make(tmp_path)
    monkeypatch.setattr(service_module, "geocode", lambda village, district, state: None)         # the lookup finds nothing
    f = s.add_farmer({"farmer_name": "Ramesh", "phone_number": "9876543210", "preferred_language": "Kannada",
                      "village": "Rajajinagar", "district": "banglore", "state": "Karnataka"})
    assert f["located"] is False
    monkeypatch.setattr(service_module, "geocode",
                        lambda village, district, state: Place(12.97, 77.59, "Bengaluru, Karnataka (district)", "district"))
    again = s.update_farmer(f["farmer_id"], {"farmer_name": "Ramesh", "village": "Rajajinagar", "district": "banglore",
                                             "state": "Karnataka"})                                  # nothing in the place changed
    assert again["located"] is True


def test_a_located_farmer_is_not_looked_up_again_when_the_place_did_not_change(tmp_path, monkeypatch):
    s = make(tmp_path)
    calls = []

    def locate(village, district, state):
        calls.append(village)
        return Place(12.52, 76.9, "Mandya (village)", "village")
    monkeypatch.setattr(service_module, "geocode", locate)
    f = s.add_farmer({"farmer_name": "Savitha", "phone_number": "9876543211", "preferred_language": "Kannada",
                      "village": "Mandya", "district": "Mandya", "state": "Karnataka"})
    s.update_farmer(f["farmer_id"], {"farmer_name": "Savitha K"})
    assert calls == ["Mandya"]                                                  # one lookup, at the start
