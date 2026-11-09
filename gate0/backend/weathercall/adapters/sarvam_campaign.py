"""Sarvam Campaigns: Sarvam owns the schedule, dialling and retries; we hand it each day's farmers.

- SarvamCampaigns talks to the API:
    POST scheduling/v1/orgs/{org}/workspaces/{ws}/campaigns                              create the campaign
    POST scheduling/v1/orgs/{org}/workspaces/{ws}/campaigns/{id}/cohorts/stream          add a day's farmers
    GET  analytics/v1/{org}/{ws}/{app}/attempts?filter_conditions=[campaign_id]          read outcomes
- CampaignStore keeps, in the same SQLite file as the ledger, the campaign we created and which farmer was
  queued for which day with which message (so a push is never repeated and results can be matched back).
Phone numbers go to Sarvam (it must dial them) but are never stored here. Analytics replies carry full numbers;
only the status fields are read.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from ..db import connect
from .sarvam_agent import BASE, _STATUS, to_e164

IST = timezone(timedelta(hours=5, minutes=30))
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class QueuedCall:
    farmer_id: str
    phone: str          # sent to Sarvam only, never stored
    language_name: str  # Hindi | Kannada | English
    message: str        # the script text, kept in the ledger as the record of what the farmer should hear
    variables: dict[str, str] = field(default_factory=dict)   # what the agent speaks from (see script.weather_variables)


class SarvamCampaigns:
    _NEEDED = ("SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID", "SARVAM_APP_ID", "SARVAM_CONNECTION_ID", "SARVAM_AGENT_PHONE")

    def __init__(self, env: dict | None = None, opener=urllib.request.urlopen):
        e = env if env is not None else os.environ
        self._key = e.get("SARVAM_AGENT_API_KEY") or e.get("SARVAM_API_KEY", "")
        missing = [k for k in self._NEEDED if not e.get(k)] + ([] if self._key else ["SARVAM_AGENT_API_KEY"])
        if missing:
            raise ValueError(f"Sarvam campaigns need {missing} in gate0/.env (see docs/SARVAM_SETUP.md)")
        self.org, self.ws, self.app = e["SARVAM_ORG_ID"], e["SARVAM_WORKSPACE_ID"], e["SARVAM_APP_ID"]
        self.app_version = int(e.get("SARVAM_APP_VERSION", 1))
        self.connection_id, self.agent_phone = e["SARVAM_CONNECTION_ID"], e["SARVAM_AGENT_PHONE"]
        self._open = opener

    def __repr__(self) -> str:
        return f"SarvamCampaigns(app={self.app!r})"

    def _request(self, url: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     method="POST" if body is not None else "GET",
                                     headers={"X-API-Key": self._key, "Content-Type": "application/json"})
        try:
            with self._open(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            # keep only Sarvam's error code: its message text can quote rejected phone numbers
            try:
                code = (json.load(exc).get("error") or {}).get("code", "")
            except Exception:
                code = ""
            raise RuntimeError(f"Sarvam API returned HTTP {exc.code} {code}".strip()) from None

    def create_campaign(self, name: str, start: date, days: int, call_time: str, window_end: str,
                        max_attempts: int, retry_gap_minutes: int) -> str:
        first = datetime.combine(start, time.fromisoformat(call_time), IST)
        last = datetime.combine(start + timedelta(days=days - 1), time.fromisoformat(window_end), IST)
        retry = {"enabled": True}
        body = {
            "name": name,
            "description": f"Gate Zero weather calls, {days} day(s) from {start.isoformat()}",
            "app_config": {
                "app_id": self.app, "app_type": "agent", "app_version": self.app_version, "attempts_per_second": 1,
                "connection_configs": [{"connection_id": self.connection_id, "phone_numbers": [self.agent_phone],
                                        "weight": 1}],
                "retry_config": {"max_retries": max(0, max_attempts - 1), "retry_interval_minutes": retry_gap_minutes,
                                 "retry_on": {"busy": retry, "no_answer": retry, "failed": retry}},
            },
            "start_timestamp": first.isoformat(), "end_timestamp": last.isoformat(),
            "allowed_schedule": {"allowed_start_time": call_time, "allowed_end_time": window_end,
                                 "allowed_days": _DAYS, "timezone": "Asia/Kolkata"},
        }
        return self._request(f"{BASE}/scheduling/v1/orgs/{self.org}/workspaces/{self.ws}/campaigns", body)["campaign_id"]

    def stream_cohort(self, campaign_id: str, name: str, calls: list[QueuedCall]) -> list[str]:
        """Adds the day's farmers, at most 1000 per request. Returns the cohort ids."""
        ids = []
        for i in range(0, len(calls), 1000):
            users = [{"user_phone_number": to_e164(c.phone), "user_identifier": c.farmer_id,
                      "app_variables": c.variables, "app_overrides": {"initial_language_name": c.language_name}}
                     for c in calls[i:i + 1000]]
            part = name if i == 0 else f"{name}-{i // 1000 + 1}"
            ids.append(self._request(f"{BASE}/scheduling/v1/orgs/{self.org}/workspaces/{self.ws}/campaigns/"
                                     f"{campaign_id}/cohorts/stream", {"name": part, "users": users})["cohort_id"])
        return ids

    def attempts(self, campaign_id: str, day: date) -> list[dict]:
        """Every dial the campaign made on that day (IST), keeping only the fields we use."""
        filters = json.dumps([{"field": "campaign_id", "operator": "equals", "value": campaign_id}])
        start = datetime.combine(day, time(0, 0), IST)
        out, offset = [], 0
        while True:
            q = urllib.parse.urlencode({"start_datetime": start.isoformat(),
                                        "end_datetime": (start + timedelta(days=1)).isoformat(),
                                        "filter_conditions": filters, "limit": 1000, "offset": offset,
                                        "sort_by": "attempted_at"})
            page = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/attempts?{q}")
            for i in page.get("items", []):        # user_contact (the full number) is never copied
                slim = {k: i.get(k) for k in ("attempt_id", "user_identifier", "connectivity_status",
                                              "duration_in_seconds", "failure_reason", "next_action_status",
                                              "retry_attempt", "interaction_id", "ended_by")}
                slim["call_summary"] = (i.get("agent_variables") or {}).get("call_summary")
                out.append(slim)
            if not page.get("next_page_uri"):
                return out
            offset += 1000

    def transcript(self, interaction_id: str) -> list[dict]:
        """Turn-by-turn transcript of one connected call, with phone-like numbers masked."""
        iid = urllib.parse.quote(interaction_id, safe="")
        data = self._request(f"{BASE}/analytics/v1/{self.org}/{self.ws}/{self.app}/transcripts/{iid}")
        return [{"turn_id": m.get("turn_id"), "role": m.get("role"), "content": scrub(m.get("content") or ""),
                 "language_name": m.get("language_name")} for m in data.get("messages") or []]


_PHONE_LIKE = re.compile(r"\+?\d[\d \-()]{8,}\d")


def scrub(text: str | None) -> str | None:
    """Masks anything that looks like a phone number (10 or more digits). Callers may say their number aloud,
    and provider error texts can quote it, so every stored free text goes through here."""
    if text is None:
        return None
    return _PHONE_LIKE.sub(lambda m: "[number removed]" if sum(c.isdigit() for c in m.group()) >= 10 else m.group(),
                           text)


def outcome(item: dict):
    """AttemptStatus for one Analytics attempt, or None when Sarvam has not settled it yet."""
    return _STATUS.get(item.get("connectivity_status") or "")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sarvam_campaigns(
  campaign_id TEXT PRIMARY KEY, start_date TEXT, days INT, call_time TEXT, window_end TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS sarvam_queue(
  farmer_id TEXT, call_date TEXT, campaign_id TEXT, cohort_id TEXT, language TEXT, message_text TEXT,
  weather_source TEXT, pushed_at TEXT, PRIMARY KEY(farmer_id, call_date));
CREATE TABLE IF NOT EXISTS call_details(
  farmer_id TEXT, call_date TEXT, attempt_id TEXT, interaction_id TEXT, ended_by TEXT, failure_reason TEXT,
  summary TEXT, transcript TEXT, fetched_at TEXT, PRIMARY KEY(farmer_id, call_date, attempt_id));
"""


class CampaignStore:
    def __init__(self, path: str = ":memory:"):
        self.db = connect(path)
        self.db.executescript(_SCHEMA)

    def save_campaign(self, campaign_id: str, start: date, days: int, call_time: str, window_end: str) -> None:
        self.db.execute("INSERT INTO sarvam_campaigns VALUES(?,?,?,?,?,?)", (
            campaign_id, start.isoformat(), days, call_time, window_end, datetime.now().isoformat(timespec="seconds")))
        self.db.commit()

    def campaign_for(self, day: date) -> dict | None:
        """The newest campaign whose days include this day."""
        for cid, start, days, call_time, window_end in self.db.execute(
                "SELECT campaign_id, start_date, days, call_time, window_end FROM sarvam_campaigns "
                "ORDER BY created_at DESC"):
            s = date.fromisoformat(start)
            if s <= day < s + timedelta(days=days):
                return {"campaign_id": cid, "start": s, "days": days, "call_time": call_time, "window_end": window_end}
        return None

    def queued_ids(self, day: date) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT farmer_id FROM sarvam_queue WHERE call_date=?",
                                              (day.isoformat(),))}

    def mark_queued(self, day: date, campaign_id: str, cohort_id: str, rows: list[tuple[str, str, str, str]]) -> None:
        """rows: (farmer_id, language, message_text, weather_source)"""
        now = datetime.now().isoformat(timespec="seconds")
        self.db.executemany("INSERT INTO sarvam_queue VALUES(?,?,?,?,?,?,?,?)", [
            (fid, day.isoformat(), campaign_id, cohort_id, lang, msg, src, now) for fid, lang, msg, src in rows])
        self.db.commit()

    def save_detail(self, farmer_id: str, day: date, attempt_id: str, interaction_id: str | None,
                    ended_by: str | None, failure_reason: str | None, summary: str | None,
                    transcript: list[dict] | None) -> None:
        """One row per Sarvam attempt for the monitoring UI. Free texts are scrubbed; a rerun changes nothing."""
        reason = None if failure_reason in (None, "", "NO_FAILURE_REASON") else scrub(failure_reason)
        self.db.execute("INSERT OR IGNORE INTO call_details VALUES(?,?,?,?,?,?,?,?,?)", (
            farmer_id, day.isoformat(), attempt_id, interaction_id, ended_by, reason, scrub(summary),
            None if transcript is None else json.dumps(transcript, ensure_ascii=False),
            datetime.now().isoformat(timespec="seconds")))
        self.db.commit()

    def queued(self, day: date) -> dict[str, dict]:
        return {fid: {"language": lang, "message": msg, "weather_source": src}
                for fid, lang, msg, src in self.db.execute(
                    "SELECT farmer_id, language, message_text, weather_source FROM sarvam_queue WHERE call_date=?",
                    (day.isoformat(),))}
