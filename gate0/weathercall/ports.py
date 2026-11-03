"""Ports: the sockets the core plugs into. Adapters implement these; the core never imports an adapter.

To join the final product, write a new adapter for FarmerSource and CallLedger (backed by Trust AI)
and CallRequest intake; weather, voice and telephony adapters carry over unchanged.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from .contracts import (
    CallAttempt, CallStatusView, FarmerContext, FarmerDayResult, Language,
    ProviderCallResult, WeatherReport,
)


@runtime_checkable
class FarmerSource(Protocol):
    """Contract 2 provider: who may be called, with approved context."""
    def list_callable_ids(self, call_date: date) -> list[str]: ...
    def get_context(self, farmer_id: str) -> FarmerContext | None: ...


@runtime_checkable
class CallLedger(Protocol):
    """Contracts 3 and 4: write what happened, read operational status."""
    def record_attempt(self, attempt: CallAttempt) -> None: ...
    def record_day_result(self, result: FarmerDayResult) -> None: ...
    def has_final_result(self, farmer_id: str, call_date: date) -> bool: ...
    def status(self, call_date: date) -> CallStatusView: ...
    def has_daily_dispatch(self, farmer_id: str, dispatch_date: date) -> bool: ...
    def create_daily_dispatch(
        self, farmer_id: str, dispatch_date: date, status: str, provider_call_id: str = "", error: str = ""
    ) -> str: ...
    def update_daily_dispatch(
        self, farmer_id: str, dispatch_date: date, status: str, provider_call_id: str = "", error: str = ""
    ) -> None: ...
    def get_daily_dispatch(self, farmer_id: str, dispatch_date: date) -> dict[str, Any] | None: ...
    def acquire_lock(self, lock_name: str, instance_id: str, timeout_seconds: int = 3600) -> bool: ...
    def release_lock(self, lock_name: str, instance_id: str) -> bool: ...


@runtime_checkable
class WeatherProvider(Protocol):
    def get_weather(self, place_name: str, latitude: float, longitude: float, call_date: date) -> WeatherReport | None: ...


@runtime_checkable
class VoiceProvider(Protocol):
    """Text to speech. Returns an opaque audio reference the telephony adapter can play."""
    def synthesize(self, text: str, language: Language) -> str: ...


@runtime_checkable
class TelephonyProvider(Protocol):
    def place_call(self, phone: str, audio_ref: str) -> ProviderCallResult: ...
