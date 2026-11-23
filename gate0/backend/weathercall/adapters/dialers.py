"""Dialers for the dashboard service: place one call for one farmer and read back what the agent recorded.

- MockDialler: no network, results are marked simulated.
- SarvamDialler: a real call through Sarvam's instant-outbound API. It sends the farmer's weather and the current date
  and time as the agent's variables; the agent opens with its own intro, so no opening message is sent. After the call
  it reads the agent's output variables and the transcript (phone-like numbers masked).

make_dialler() picks Sarvam when GATE0_TELEPHONY=sarvam_agent and the Sarvam settings are complete, else the mock,
and says why, so the dashboard can show which one is live.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from ..contracts import ProviderCallResult
from .mock import MockTelephony
from .sarvam_agent import BASE, SarvamAgentTelephony, _result_from, to_e164
from .sarvam_campaign import scrub

def _strip_quoted(text: str) -> str:
    """Quoted values in an error message could be a farmer's details: they are replaced."""
    return re.sub(r"""(['"]).*?\1""", "'...'", text or "")


class SarvamHTTPError(RuntimeError):
    """Sarvam answered a cohort push with an error. safe_text is the HTTP code and Sarvam's error code, never its message
    (a message can quote a phone number)."""

    def __init__(self, safe_text: str):
        super().__init__(safe_text)
        self.safe_text = safe_text


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """A multipart/form-data body (standard library only). fields: name -> text; files: name -> (file name, type, bytes)."""
    boundary = uuid.uuid4().hex
    crlf = b"\r\n"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f'--{boundary}'.encode() + crlf + f'Content-Disposition: form-data; name="{name}"'.encode() + crlf + crlf + str(value).encode() + crlf)
    for name, (filename, ctype, data) in files.items():
        parts.append(f'--{boundary}'.encode() + crlf + f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode() + crlf
                     + f'Content-Type: {ctype}'.encode() + crlf + crlf + data + crlf)
    parts.append(f'--{boundary}--'.encode() + crlf)
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


OUTPUT_VARS = ("call_summary", "callback_time", "understood_weather", "stop_calls_requested")


class MockDialler:
    mode = "mock (simulated)"
    live = False

    def place(self, phone, language_name, variables) -> ProviderCallResult:
        return MockTelephony().place_call(phone, "mock")

    def find_call(self, phone, start, end):
        return None                                  # simulated calls leave no record anywhere else

    inbound_ready = False                            # no inbound line in simulation

    def push_inbound_many(self, entries, cohort_name) -> list[str]:
        return []

    def find_inbound_calls(self, start, end, known_ids):
        return []

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

    def push_inbound_many(self, entries, cohort_name) -> list[str]:
        """Tells the inbound deployment which numbers may ring and what to say to each: Sarvam matches a caller by number
        (a cohort of known callers) and starts the agent with that person's variables. entries: dicts with phone, fid,
        language_name and variables. Sent as one CSV cohort upload (POST .../deployments/{id}/cohorts/upload): Sarvam refuses
        the JSON 'stream' route for deployments with 'User Identifier is not supported' even when no identifier is sent (found
        23 Nov), while the upload is accepted. Returns the cohort id."""
        if not self.inbound_ready:
            raise RuntimeError("SARVAM_INBOUND_DEPLOYMENT_ID is not set")
        url = f"{BASE}/scheduling/v1/orgs/{self.org}/workspaces/{self.ws}/deployments/{self.inbound_deployment}/cohorts/upload"
        rows, seen = [], set()
        for e in entries:
            try:
                phone = to_e164(e["phone"])
            except ValueError:                              # a number that cannot be dialled is left out, not the whole list
                continue
            if phone in seen:                               # two farmers on one number: the line can know only one of them
                continue
            seen.add(phone)
            rows.append((phone, e["language_name"], e["variables"]))
        if not rows:
            return []
        names = sorted({k for _, _, v in rows for k in v})              # the agent's variable names, one CSV column each
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["phone", "language", *names])
        for phone, language, variables in rows:
            writer.writerow([phone, language, *[str(variables.get(k, "")) for k in names]])
        transformation = {"phone_number": {"column_name": "phone", "country_code": "IN"},
                          "app_variables": {k: {"column_name": k} for k in names},
                          "app_overrides": {"initial_language_name": {"column_name": "language"}}}
        body, content_type = _multipart({"name": cohort_name[:50]}, {
            "cohort_file": ("cohort.csv", "text/csv", out.getvalue().encode("utf-8")),
            "cohort_transformation_file": ("transformation.json", "application/json", json.dumps(transformation).encode("utf-8"))})
        req = urllib.request.Request(url, data=body, method="POST", headers={"X-API-Key": self._key, "Content-Type": content_type})
        try:
            with self._open(req, timeout=60) as resp:
                return [str(json.load(resp).get("cohort_id", ""))]
        except urllib.error.HTTPError as exc:
            code, message = "", ""
            try:
                err = json.load(exc).get("error") or {}
                code, message = str(err.get("code", "")), str(err.get("message") or "")
                details = (err.get("data") or {}).get("details")        # Sarvam puts the real reason here
                if isinstance(details, str) and details:
                    message = f"{message} {details}".strip() if message else details
                elif isinstance(details, (list, dict)) and details:
                    message = f"{message} {json.dumps(details)}".strip()
            except Exception:
                pass
            detail = f"HTTP {exc.code} {code}".strip()
            if message:             # Sarvam's own words say which field it did not like; digits and quoted values are masked
                detail += ": " + _strip_quoted(scrub(message))[:140]
            raise SarvamHTTPError(f"{detail[:170]} [upload columns: {', '.join(['phone', 'language', *names])}]") from None

    def find_inbound_calls(self, start, end, known_ids):
        """Connected calls between start and end that are not ours (not in known_ids): farmers ringing the line. Returns
        (last 4 digits of the caller, result, when it ended in UTC, SHA-256 of the caller's +91 number as Sarvam gives it),
        oldest first. The hash identifies a caller exactly without handling the number; the last 4 digits are only a fallback."""
        found, offset = [], 0
        while True:
            q = urllib.parse.urlencode({"start_datetime": start.astimezone(timezone.utc).isoformat(timespec="seconds"),
                                        "end_datetime": end.astimezone(timezone.utc).isoformat(timespec="seconds"),
                                        "limit": 1000, "offset": offset, "sort_by": "attempted_at"})
            page = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/attempts?{q}")
            for item in page.get("items", []):
                # Only incoming calls to the line should be returned; ignore outbound calls placed to farmers
                direction = (item.get("channel_direction") or "").lower().strip()
                if direction and direction != "inbound":
                    continue
                # a call to the line has the same attempt_id ("NO_JOB_ID") every time: it is known by its interaction id
                call_id = (item.get("interaction_id") if direction == "inbound"
                           else item.get("attempt_id") or item.get("interaction_id")) or ""
                if not call_id or call_id in known_ids:
                    continue
                result = _result_from(item, call_id)
                if result is None or result.status.value != "answered":
                    continue
                began = datetime.fromisoformat(str(item["attempted_at"]).replace("Z", "")).replace(tzinfo=timezone.utc)
                last4 = re.sub(r"\D", "", str(item.get("user_contact_masked") or ""))[-4:]
                found.append((last4, result, began + timedelta(seconds=result.duration_s or 0), str(item.get("user_contact_hashed") or "")))
            if not page.get("next_page_uri"):
                return found
            offset += 1000

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
        incoming = "/" in attempt_id                         # a call to the line is known by its interaction id (YYYYMMDD/...)
        key = "interaction_id" if incoming else "attempt_id"
        filters = json.dumps([{"field": key, "operator": "equals", "value": attempt_id}])
        for _ in range(20):                                 # up to a minute, looking every 3 s so the notes show as soon as they are in
            q = urllib.parse.urlencode({
                "start_datetime": (self._now() - timedelta(hours=24 if incoming else 1)).isoformat(timespec="seconds"),
                "end_datetime": (self._now() + timedelta(minutes=5)).isoformat(timespec="seconds"),
                "filter_conditions": filters, "limit": 5})
            items = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/attempts?{q}").get("items", [])
            item = next((i for i in items if i.get(key) == attempt_id), {})
            got = {k: scrub((item.get("agent_variables") or {}).get(k)) for k in OUTPUT_VARS}
            if got.get("call_summary"):
                got["transcript"] = self._transcript(item.get("interaction_id"))
                return got
            self._sleep(self.poll_every(3))
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
