"""Dialers for the dashboard service: place one call for one farmer and read back what the agent recorded.

- MockDialler: no network, results are marked simulated.
- SarvamDialler: a real call through Sarvam's instant-outbound API. It sends the farmer's weather and the current date
  and time as the agent's variables; the agent opens with its own intro, so no opening message is sent. After the call
  it reads the agent's output variables and the transcript (phone-like numbers masked).

make_dialler() picks Sarvam when GATE0_TELEPHONY=sarvam_agent and the Sarvam settings are complete, else the mock,
and says why, so the dashboard can show which one is live.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from ..contracts import ProviderCallResult
from .mock import MockTelephony
from .sarvam_agent import BASE, SarvamAgentTelephony, _result_from, to_e164
from .sarvam_campaign import scrub

OUTPUT_VARS = ("call_summary", "callback_time", "understood_weather", "stop_calls_requested")


class MockDialler:
    mode = "mock (simulated)"
    live = False

    def place(self, phone, language_name, variables) -> ProviderCallResult:
        return MockTelephony().place_call(phone, "mock")

    def find_call(self, phone, start, end):
        return None                                  # simulated calls leave no record anywhere else

    inbound_ready = False                            # no inbound line in simulation

    def push_inbound(self, phone, farmer_id, language_name, variables, cohort_name) -> str:
        return ""

    def find_inbound(self, phone, start, end, known_ids):
        return None

    def outputs(self, attempt_id: str) -> dict:
        return {"call_summary": "(simulated) the farmer heard the weather update and said they understood.",
                "callback_time": "", "understood_weather": "yes", "stop_calls_requested": "no",
                "transcript": [{"speaker": "Agent", "text": "(simulated call, no real conversation)"}]}


class SarvamDialler(SarvamAgentTelephony):
    mode = "Sarvam"
    live = True

    def __init__(self, env: dict | None = None, **kw):
        super().__init__(env=env, **kw)
        e = env if env is not None else os.environ
        self.inbound_deployment = (e.get("SARVAM_INBOUND_DEPLOYMENT_ID") or "").strip()   # the inbound deployment farmers call back on

    @property
    def inbound_ready(self) -> bool:
        return bool(self.inbound_deployment)

    def push_inbound(self, phone, farmer_id, language_name, variables, cohort_name) -> str:
        """Tells the inbound deployment who this number is: when it calls in, the agent starts with these variables.
        Sarvam matches the caller by number (a cohort of known callers). Returns the cohort id."""
        if not self.inbound_ready:
            raise RuntimeError("SARVAM_INBOUND_DEPLOYMENT_ID is not set")
        body = {"name": cohort_name, "users": [{"user_phone_number": to_e164(phone), "user_identifier": farmer_id,
                                                  "app_variables": variables,
                                                  "app_overrides": {"initial_language_name": language_name}}]}
        url = f"{BASE}/scheduling/v1/orgs/{self.org}/workspaces/{self.ws}/deployments/{self.inbound_deployment}/cohorts/stream"
        return str(self._request(url, body).get("cohort_id", ""))

    def find_inbound(self, phone, start, end, known_ids):
        """A connected call from this number (last 4 digits) between start and end that is not one of ours: the
        farmer calling back. Returns (result, when it ended in UTC) or None."""
        last4 = re.sub(r"\D", "", phone or "")[-4:]
        q = urllib.parse.urlencode({"start_datetime": start.astimezone(timezone.utc).isoformat(timespec="seconds"),
                                    "end_datetime": end.astimezone(timezone.utc).isoformat(timespec="seconds"), "limit": 100})
        items = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/attempts?{q}").get("items", [])
        mine = sorted((i for i in items if last4 and str(i.get("user_contact_masked") or "")[-4:] == last4
                       and i.get("attempt_id") not in known_ids), key=lambda i: i.get("attempted_at") or "")
        for item in mine:
            result = _result_from(item, item.get("attempt_id") or "")
            if result is not None and result.status.value == "answered":
                began = datetime.fromisoformat(str(item["attempted_at"]).replace("Z", "")).replace(tzinfo=timezone.utc)
                return result, began + timedelta(seconds=result.duration_s or 0)
        return None

    def place(self, phone, language_name, variables) -> ProviderCallResult:
        started = self._now()
        created = self._request(f"{BASE}/outbounds/v1/orgs/{self.org}/workspaces/{self.ws}/outbounds", {
            "app_config": {
                "app_id": self.app, "app_version": self.app_version,
                "connection_config": {"connection_id": self.connection_id, "agent_phone_number": self.agent_phone},
                "agent_variables": variables,
                "app_overrides": {"initial_language_name": language_name},
            },
            "user_config": {"user_phone_number": to_e164(phone)},
        })
        return self._wait_for_outcome(created["attempt_id"], started)

    def outputs(self, attempt_id: str) -> dict:
        """The agent's output variables (Sarvam fills them a little after the call ends) and the transcript."""
        filters = json.dumps([{"field": "attempt_id", "operator": "equals", "value": attempt_id}])
        for _ in range(6):
            q = urllib.parse.urlencode({
                "start_datetime": (self._now() - timedelta(hours=1)).isoformat(timespec="seconds"),
                "end_datetime": (self._now() + timedelta(minutes=5)).isoformat(timespec="seconds"),
                "filter_conditions": filters, "limit": 5})
            items = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/attempts?{q}").get("items", [])
            item = next((i for i in items if i.get("attempt_id") == attempt_id), {})
            got = {k: scrub((item.get("agent_variables") or {}).get(k)) for k in OUTPUT_VARS}
            if got.get("call_summary"):
                got["transcript"] = self._transcript(item.get("interaction_id"))
                return got
            self._sleep(10)
        return {}

    def _transcript(self, interaction_id: str | None) -> list[dict]:
        if not interaction_id:
            return []
        try:
            iid = urllib.parse.quote(interaction_id, safe="")
            data = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/transcripts/{iid}")
        except Exception:
            return []
        return [{"speaker": "Agent" if m.get("role") == "assistant" else "Farmer", "text": scrub(m.get("content") or "")}
                for m in data.get("messages") or [] if m.get("content")]


def make_dialler(env: dict | None = None):
    e = env if env is not None else os.environ
    if e.get("GATE0_TELEPHONY") == "sarvam_agent":
        try:
            return SarvamDialler(env=e), ""
        except ValueError as exc:
            return MockDialler(), f"Sarvam is not configured yet, using mock ({exc})"
    return MockDialler(), "GATE0_TELEPHONY is not sarvam_agent, using mock"
