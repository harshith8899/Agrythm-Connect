"""Calls through a Sarvam Voice Agent (Samvaad). The agent speaks our script, so no separate TTS step is needed.

Pair them in .env:  GATE0_VOICE=sarvam_agent  GATE0_TELEPHONY=sarvam_agent
- SarvamAgentVoice does no synthesis; it packs the message and language into the audio reference.
- SarvamAgentTelephony places an instant outbound call with that message as the agent's first line, then polls
  the Analytics API until the attempt has an outcome. Setup of the agent itself: docs/SARVAM_SETUP.md.

API: POST https://apps.sarvam.ai/api/outbounds/v1/orgs/{org}/workspaces/{ws}/outbounds  (header X-API-Key)
     GET  https://apps.sarvam.ai/api/analytics/v1/{org}/{ws}/{app}/attempts?filter_conditions=[attempt_id]
Analytics responses carry the farmer's full phone number; only the status fields are read and nothing is kept.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from ..contracts import AttemptStatus, Language, ProviderCallResult

BASE = "https://apps.sarvam.ai/api"
_LANG_NAMES = {Language.HI: "Hindi", Language.EN: "English", Language.KN: "Kannada"}
_STATUS = {"connected": AttemptStatus.ANSWERED, "no_answer": AttemptStatus.NO_ANSWER,
           "busy": AttemptStatus.BUSY, "failed": AttemptStatus.FAILED}


class SarvamAgentVoice:
    def synthesize(self, text: str, language: Language) -> str:
        return json.dumps({"text": text, "language": _LANG_NAMES[language]}, ensure_ascii=False)


def to_e164(phone: str, country_code: str = "91") -> str:
    digits = re.sub(r"\D", "", phone)
    if phone.strip().startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return f"+{country_code}{digits}"
    if len(digits) == 12 and digits.startswith(country_code):
        return "+" + digits
    raise ValueError("phone number is not a 10-digit Indian mobile or E.164 number")


class SarvamAgentTelephony:
    _NEEDED = ("SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID", "SARVAM_APP_ID", "SARVAM_CONNECTION_ID", "SARVAM_AGENT_PHONE")

    def __init__(self, env: dict | None = None, opener=urllib.request.urlopen, sleep=time.sleep, now=None):
        e = env if env is not None else os.environ
        self._key = e.get("SARVAM_AGENT_API_KEY") or e.get("SARVAM_API_KEY", "")
        missing = [k for k in self._NEEDED if not e.get(k)] + ([] if self._key else ["SARVAM_AGENT_API_KEY"])
        if missing:
            raise ValueError(f"Sarvam agent calling needs {missing} in gate0/.env (see docs/SARVAM_SETUP.md)")
        self.org, self.ws, self.app = e["SARVAM_ORG_ID"], e["SARVAM_WORKSPACE_ID"], e["SARVAM_APP_ID"]
        self.app_version = int(e.get("SARVAM_APP_VERSION", 1))
        self.connection_id, self.agent_phone = e["SARVAM_CONNECTION_ID"], e["SARVAM_AGENT_PHONE"]
        self.poll_seconds = int(e.get("SARVAM_POLL_SECONDS", 20))
        self.timeout_seconds = int(e.get("SARVAM_CALL_TIMEOUT_SECONDS", 300))
        self._open, self._sleep = opener, sleep
        self._now = now or (lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"SarvamAgentTelephony(app={self.app!r})"

    def _request(self, url: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     method="POST" if body is not None else "GET",
                                     headers={"X-API-Key": self._key, "Content-Type": "application/json"})
        with self._open(req, timeout=30) as resp:
            return json.load(resp)

    def place_call(self, phone: str, audio_ref: str) -> ProviderCallResult:
        msg = json.loads(audio_ref)
        started = self._now()
        created = self._request(f"{BASE}/outbounds/v1/orgs/{self.org}/workspaces/{self.ws}/outbounds", {
            "app_config": {
                "app_id": self.app, "app_version": self.app_version,
                "connection_config": {"connection_id": self.connection_id, "agent_phone_number": self.agent_phone},
                "agent_variables": {"weather_message": msg["text"]},
                "app_overrides": {"initial_bot_message": msg["text"], "initial_language_name": msg["language"]},
            },
            "user_config": {"user_phone_number": to_e164(phone)},
        })
        attempt_id = created["attempt_id"]
        return self._wait_for_outcome(attempt_id, started)

    def _wait_for_outcome(self, attempt_id: str, started: datetime) -> ProviderCallResult:
        filters = json.dumps([{"field": "attempt_id", "operator": "equals", "value": attempt_id}])
        waited = 0
        while waited < self.timeout_seconds:
            self._sleep(self.poll_seconds)
            waited += self.poll_seconds
            # end time moves each poll, so the 60 s response cache never hands back a stale page
            q = urllib.parse.urlencode({
                "start_datetime": (started - timedelta(minutes=5)).isoformat(timespec="seconds"),
                "end_datetime": (self._now() + timedelta(minutes=5)).isoformat(timespec="seconds"),
                "filter_conditions": filters, "limit": 5,
            })
            items = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/attempts?{q}").get("items", [])
            item = next((i for i in items if i.get("attempt_id") == attempt_id), None)
            status = _STATUS.get((item or {}).get("connectivity_status") or "")
            if status is None:
                continue
            reason = item.get("failure_reason") or ""
            return ProviderCallResult(
                status=status, provider_call_id=attempt_id, duration_s=int(item.get("duration_in_seconds") or 0),
                error="" if reason in ("", "NO_FAILURE_REASON") else reason[:80],
            )
        return ProviderCallResult(AttemptStatus.FAILED, provider_call_id=attempt_id, error="outcome_not_reported_in_time")
