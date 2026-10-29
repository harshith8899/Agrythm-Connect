"""Adapter registry: choose implementations by name from environment settings."""
from __future__ import annotations

import os

from ..config import load_env
from ..engine import Ports
from .local import InMemoryFarmerSource, SQLiteLedger, demo_farmers
from .mock import MockTelephony, MockVoice, MockWeather
from .open_meteo import OpenMeteoWeather
from .trust_ai_stub import TrustAIFarmerSource, TrustAILedger

_FARMERS = {"local": lambda: InMemoryFarmerSource(demo_farmers()), "trust_ai": TrustAIFarmerSource}
_LEDGER = {"local": lambda: SQLiteLedger(os.environ.get("GATE0_DB", ":memory:")), "trust_ai": TrustAILedger}
_WEATHER = {
    "mock": MockWeather,
    "open-meteo": OpenMeteoWeather,
    "open_meteo": OpenMeteoWeather,
}
_VOICE = {"mock": MockVoice}
_TELEPHONY = {"mock": MockTelephony}


def build_ports() -> Ports:
    load_env()

    def pick(table, var, default, alt_var=None):
        name = os.environ.get(var)
        if name is None and alt_var:
            name = os.environ.get(alt_var)
        if name is None:
            name = default
        if name not in table:
            raise ValueError(f"{var}={name!r} is not available. Options: {sorted(table)}")
        return table[name]()
    return Ports(
        farmers=pick(_FARMERS, "GATE0_FARMERS", "local"),
        ledger=pick(_LEDGER, "GATE0_LEDGER", "local"),
        weather=pick(_WEATHER, "GATE0_WEATHER", "mock", alt_var="GATEO_WEATHER"),
        voice=pick(_VOICE, "GATE0_VOICE", "mock"),
        telephony=pick(_TELEPHONY, "GATE0_TELEPHONY", "mock"),
    )
