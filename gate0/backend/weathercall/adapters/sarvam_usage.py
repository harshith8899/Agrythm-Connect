"""Read-only look at Sarvam's call records: what was dialled, how long each call lasted, why a call failed.

Sarvam documents no endpoint for the credit balance, so the dashboard shows only what these records give (calls,
billed minutes and an estimated amount); the balance is on Sarvam's Settings -> Billing page. Phone numbers in the failure text are masked
and the full number Sarvam returns in each record (`user_contact`) is never read.
"""
from __future__ import annotations

import os
import urllib.parse
from datetime import datetime

from .sarvam_agent import BASE
from .sarvam_campaign import SarvamCampaigns, scrub

_FIELDS = ("attempted_at", "connectivity_status", "duration_in_seconds", "app_version")


class SarvamUsage(SarvamCampaigns):
    def __repr__(self) -> str:
        return f"SarvamUsage(app={self.app!r})"

    def attempts_between(self, start: datetime, end: datetime) -> list[dict]:
        """Every attempt in the window (timezone-aware datetimes), with only the fields we use."""
        out, offset = [], 0
        while True:
            q = urllib.parse.urlencode({"start_datetime": start.isoformat(timespec="seconds"),
                                        "end_datetime": end.isoformat(timespec="seconds"),
                                        "limit": 1000, "offset": offset, "sort_by": "attempted_at"})
            page = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/attempts?{q}")
            for i in page.get("items", []):
                slim = {k: i.get(k) for k in _FIELDS}
                reason = i.get("failure_reason")
                slim["failure_reason"] = None if reason in (None, "", "NO_FAILURE_REASON") else scrub(str(reason))
                out.append(slim)
            if not page.get("next_page_uri"):
                return out
            offset += 1000


def make_usage(env: dict | None = None) -> SarvamUsage | None:
    """The reader when the Sarvam settings in .env are complete, else None (simulated mode)."""
    e = env if env is not None else os.environ
    if e.get("GATE0_TELEPHONY") != "sarvam_agent":
        return None
    try:
        return SarvamUsage(env=e)
    except ValueError:
        return None
