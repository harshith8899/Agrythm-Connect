import pytest

from weathercall import ports as P
from weathercall.adapters import build_ports
from weathercall.adapters.local import InMemoryFarmerSource, SQLiteLedger, demo_farmers
from weathercall.adapters.mock import DEMO_WEATHER, MockTelephony, MockVoice, MockWeather
from weathercall.adapters.open_meteo import OpenMeteoWeather
from weathercall.adapters.trust_ai_stub import TrustAIFarmerSource, TrustAILedger
from weathercall.config import Settings
from weathercall.contracts import Language
from weathercall.script import build_message, estimate_seconds


@pytest.mark.parametrize("farmer_idx", [0, 1])  # one Hindi, one English
def test_message_says_ai_and_fits_target_length(farmer_idx):
    farmer = demo_farmers()[farmer_idx]
    text = build_message(farmer, DEMO_WEATHER["Mandya"])
    s = Settings()
    assert s.target_seconds_min <= estimate_seconds(text) <= s.target_seconds_max, estimate_seconds(text)
    assert farmer.display_name in text
    assert ("AI" in text) if farmer.language is Language.EN else ("एआई" in text)


def test_every_adapter_satisfies_its_port():
    assert isinstance(InMemoryFarmerSource([]), P.FarmerSource)
    assert isinstance(SQLiteLedger(), P.CallLedger)
    assert isinstance(MockWeather(), P.WeatherProvider)
    assert isinstance(OpenMeteoWeather(), P.WeatherProvider)
    assert isinstance(MockVoice(), P.VoiceProvider)
    assert isinstance(MockTelephony(), P.TelephonyProvider)
    # the Trust AI placeholders must already fit the same sockets
    assert isinstance(TrustAIFarmerSource(), P.FarmerSource)
    assert isinstance(TrustAILedger(), P.CallLedger)


def test_registry_rejects_unknown_adapter(monkeypatch):
    monkeypatch.setenv("GATE0_WEATHER", "nope")
    with pytest.raises(ValueError):
        build_ports()


def test_registry_accepts_open_meteo_aliases(monkeypatch):
    monkeypatch.setenv("GATE0_WEATHER", "open-meteo")
    ports = build_ports()
    assert isinstance(ports.weather, OpenMeteoWeather)

    monkeypatch.setenv("GATE0_WEATHER", "open_meteo")
    ports = build_ports()
    assert isinstance(ports.weather, OpenMeteoWeather)

    monkeypatch.delenv("GATE0_WEATHER", raising=False)
    monkeypatch.setenv("GATEO_WEATHER", "open_meteo")
    ports = build_ports()
    assert isinstance(ports.weather, OpenMeteoWeather)


def test_core_never_imports_adapters():
    import pathlib
    root = pathlib.Path(__file__).parent.parent / "weathercall"
    for name in ("engine.py", "ports.py", "contracts.py", "script.py", "config.py"):
        assert "import adapters" not in (root / name).read_text(encoding="utf-8") and "from .adapters" not in (root / name).read_text(encoding="utf-8"), name
