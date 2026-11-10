"""Adapter registry: choose implementations by name from environment settings."""
from __future__ import annotations

import os

from ..engine import Ports
from .local import InMemoryFarmerSource, SQLiteLedger, demo_farmers
from .mock import MockTelephony, MockVoice, MockWeather
from .trust_ai_stub import TrustAIFarmerSource, TrustAILedger


def _sheet():
    from .sheet import SheetFarmerSource
    path = os.environ.get("GATE0_FARMERS_FILE", "")
    if not path:
        raise ValueError("GATE0_FARMERS=sheet needs GATE0_FARMERS_FILE (path to the CSV or Excel sheet)")
    geocoder = None
    if os.environ.get("GATE0_WEATHER", "mock") != "mock":   # real weather needs real coordinates
        from .weatherapi import geocode
        geocoder = geocode
    return SheetFarmerSource(path, geocoder)


def _stored(inner):
    from .weather_store import StoredWeather
    # waits between weather retries after a provider failure: 15 min, then 30 more, then 60 more (client rule)
    waits = tuple(int(x) for x in os.environ.get("GATE0_WEATHER_RETRY_MINUTES", "15,30,60").split(",") if x.strip())
    return StoredWeather(inner, os.environ.get("GATE0_DB", ":memory:"), waits)


def _open_meteo():
    from .open_meteo import OpenMeteoWeather
    return _stored(OpenMeteoWeather())


def _weatherapi():
    from .weatherapi import WeatherApiWeather
    return _stored(WeatherApiWeather())


def _sarvam():
    from .sarvam import SarvamVoice
    return SarvamVoice()


def _sarvam_agent(kind):
    from . import sarvam_agent
    return sarvam_agent.SarvamAgentVoice() if kind == "voice" else sarvam_agent.SarvamAgentTelephony()


_FARMERS = {"local": lambda: InMemoryFarmerSource(demo_farmers()), "sheet": _sheet, "trust_ai": TrustAIFarmerSource}
_LEDGER = {"local": lambda: SQLiteLedger(os.environ.get("GATE0_DB", ":memory:")), "trust_ai": TrustAILedger}
_WEATHER = {"mock": MockWeather, "open_meteo": _open_meteo, "weatherapi": _weatherapi}
_VOICE = {"mock": MockVoice, "sarvam": _sarvam, "sarvam_agent": lambda: _sarvam_agent("voice")}
_TELEPHONY = {"mock": MockTelephony, "sarvam_agent": lambda: _sarvam_agent("telephony")}


def build_ports() -> Ports:
    def pick(table, var, default):
        name = os.environ.get(var, default)
        if name not in table:
            raise ValueError(f"{var}={name!r} is not available. Options: {sorted(table)}")
        return table[name]()
    return Ports(
        farmers=pick(_FARMERS, "GATE0_FARMERS", "local"),
        ledger=pick(_LEDGER, "GATE0_LEDGER", "local"),
        weather=pick(_WEATHER, "GATE0_WEATHER", "mock"),
        voice=pick(_VOICE, "GATE0_VOICE", "mock"),
        telephony=pick(_TELEPHONY, "GATE0_TELEPHONY", "mock"),
    )
