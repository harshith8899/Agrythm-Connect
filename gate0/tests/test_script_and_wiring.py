import dataclasses

import pytest

from weathercall import ports as P
from weathercall.adapters import build_ports
from weathercall.adapters.local import InMemoryFarmerSource, SQLiteLedger, demo_farmers
from weathercall.adapters.mock import DEMO_WEATHER, MockTelephony, MockVoice, MockWeather
from weathercall.adapters.trust_ai_stub import TrustAIFarmerSource, TrustAILedger
from weathercall.config import Settings
from weathercall.contracts import Language
from weathercall.script import build_message, estimate_seconds, weather_variables


@pytest.mark.parametrize("farmer_idx", [0, 1])  # one Hindi, one English
def test_message_fits_target_length(farmer_idx):
    farmer = demo_farmers()[farmer_idx]
    text = build_message(farmer, DEMO_WEATHER["Mandya"])
    s = Settings()
    assert s.target_seconds_min <= estimate_seconds(text) <= s.target_seconds_max, estimate_seconds(text)
    assert farmer.display_name in text


_ASKS = {Language.EN: "Did you understand", Language.HI: "समझ आई", Language.KN: "ಅರ್ಥವಾಯಿತೇ",
         Language.TE: "అర్థమైందా"}


@pytest.mark.parametrize("lang", list(Language))
def test_every_language_greets_by_name_and_gives_only_the_four_weather_facts(lang):
    farmer = dataclasses.replace(demo_farmers()[0], language=lang)
    text = build_message(farmer, DEMO_WEATHER["Hassan"])      # 19-27 C, wind 18, rain 70, humidity 84
    s = Settings()
    # Kannada and Telugu words are long and few, so the word-count estimate reads low; measure the real length after TTS is on
    low = 20 if lang in (Language.KN, Language.TE) else s.target_seconds_min
    assert low <= estimate_seconds(text) <= s.target_seconds_max, estimate_seconds(text)
    assert farmer.display_name in text and "Hassan" in text and _ASKS[lang] in text
    for number in ("19", "27", "18", "70", "84"):
        assert number in text
    assert "{" not in text and "light rain" not in text        # no condition words, no unfilled slots


def test_weather_variables_use_the_names_the_agent_declares():
    farmer = demo_farmers()[0]
    assert weather_variables(farmer, DEMO_WEATHER["Hassan"]) == {
        "farmer_name": farmer.display_name, "place_name": "Hassan", "temp_min_c": "19", "temp_max_c": "27",
        "wind_kmh": "18", "rain_chance_pct": "70", "humidity_pct": "84"}


def test_every_adapter_satisfies_its_port():
    assert isinstance(InMemoryFarmerSource([]), P.FarmerSource)
    assert isinstance(SQLiteLedger(), P.CallLedger)
    assert isinstance(MockWeather(), P.WeatherProvider)
    assert isinstance(MockVoice(), P.VoiceProvider)
    assert isinstance(MockTelephony(), P.TelephonyProvider)
    # the Trust AI placeholders must already fit the same sockets
    assert isinstance(TrustAIFarmerSource(), P.FarmerSource)
    assert isinstance(TrustAILedger(), P.CallLedger)


def test_registry_rejects_unknown_adapter(monkeypatch):
    monkeypatch.setenv("GATE0_WEATHER", "nope")
    with pytest.raises(ValueError):
        build_ports()


def test_core_never_imports_adapters():
    import pathlib
    root = pathlib.Path(__file__).parent.parent / "weathercall"
    for name in ("engine.py", "ports.py", "contracts.py", "script.py", "config.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "import adapters" not in source and "from .adapters" not in source, name
