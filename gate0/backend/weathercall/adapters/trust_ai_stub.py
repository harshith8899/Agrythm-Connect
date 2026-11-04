"""Placeholder sockets for the final product (Trust AI). Not implemented on purpose.

When the platform is ready, implement these two classes against its API and select them with
GATE0_FARMERS=trust_ai and GATE0_LEDGER=trust_ai. The engine, script, weather, voice and telephony code stay as they are.
See docs/INTEGRATION.md for the field-by-field mapping.
"""
from __future__ import annotations

from datetime import date

from ..contracts import CallAttempt, CallStatusView, FarmerContext, FarmerDayResult


class TrustAIFarmerSource:
    def list_callable_ids(self, call_date: date) -> list[str]:
        raise NotImplementedError("Wire to the 'get approved farmer context' endpoint")

    def get_context(self, farmer_id: str) -> FarmerContext | None:
        raise NotImplementedError("Wire to the 'get approved farmer context' endpoint")


class TrustAILedger:
    def record_attempt(self, attempt: CallAttempt) -> None:
        raise NotImplementedError("Wire to the 'write call attempts/results' endpoint")

    def record_day_result(self, result: FarmerDayResult) -> None:
        raise NotImplementedError("Wire to the 'write call attempts/results' endpoint")

    def has_final_result(self, farmer_id: str, call_date: date) -> bool:
        raise NotImplementedError

    def status(self, call_date: date) -> CallStatusView:
        raise NotImplementedError("Wire to the 'view operational status' endpoint")
