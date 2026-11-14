"""The System tab: is everything connected, and how much has been used.

Checks: backend, database, weather API (Open-Meteo), Sarvam API and the phone line, each ok, fail or off (not set up).
Usage: calls and billed minutes counted from Sarvam's own call records, the way Sarvam bills them: each connected call
in started 60-second minutes (45 s = 1, 61 s = 2); calls that were not picked up, were busy or failed cost nothing.
Sarvam has no endpoint for the credit balance (it is only on Settings -> Billing, "Credits Left"), so no balance or
remaining credits are shown or guessed here. The amount is an estimate: billed minutes times a per-minute rate (Sarvam's
pay-as-you-go ₹3.50 by default, before GST; editable for another plan). An "insufficient quota" answer is flagged.
"""
from __future__ import annotations

import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

from .adapters.weatherapi import make_weather
from .db import OperationalError, is_postgres
from .adapters.sarvam_campaign import IST, scrub
from .adapters.sarvam_usage import make_usage

UTC = timezone.utc
CACHE_SECONDS = 30
DEFAULT_RATE = 3.5                          # INR a minute: Sarvam pay-as-you-go, before GST (Pro 3.25, Growth 3.15)
MAX_RATE = 1000.0
USAGE_DAYS = 60
_AUTO = object()
_EXHAUSTED = re.compile(r"insufficient[_ ]quota|\b402\b", re.I)


TELEPHONY_PULSE_SECONDS = 30          # Sarvam telephony is metered in started 30-second pulses of connected calls
TELEPHONY_PULSE_RATE = 0.20           # INR a pulse, before GST (docs.sarvam.ai/voice-agents/pricing), the same on every plan


def telephony_pulses(status: str, seconds) -> int:
    """Started 30-second pulses of a connected call (45 s = 2); unanswered, busy and failed calls cost nothing."""
    s = float(seconds or 0)
    return math.ceil(s / TELEPHONY_PULSE_SECONDS) if status == "connected" and s > 0 else 0


def billed_minutes(status: str, seconds) -> int:
    """Started 60-second minutes of a connected call; unanswered, busy and failed calls cost nothing."""
    s = float(seconds or 0)
    return math.ceil(s / 60) if status == "connected" and s > 0 else 0


def _when(attempt: dict) -> datetime:
    return datetime.fromisoformat(str(attempt["attempted_at"])).replace(tzinfo=UTC)     # Sarvam times are UTC


def _reason_text(reason: str) -> str:
    """The readable part of a provider error (the message inside the JSON), numbers masked and shortened."""
    m = re.search(r'"(?:Message|message|details)"\s*:\s*"([^"]+)"', reason or "")
    return scrub(m.group(1) if m else reason or "")[:160]


class SystemChecks:
    def __init__(self, service, usage=_AUTO, weather=None, now=None, env=None):
        self.service = service
        self.env = env if env is not None else os.environ
        self.usage_reader = make_usage() if usage is _AUTO else usage
        self.weather = weather or make_weather(self.env)
        self._now = now or service._now
        self._lock = threading.Lock()
        self._checks_cache: tuple[float, dict] | None = None
        self._usage_cache: tuple[float, list[dict] | None, str] | None = None

    # -- Sarvam call records (cached briefly: the tab polls) ----------------------------------------------------
    def _attempts(self, refresh: bool = False) -> tuple[list[dict] | None, str]:
        if self.usage_reader is None:
            return None, "not configured"
        with self._lock:
            if not refresh and self._usage_cache and time.monotonic() - self._usage_cache[0] < CACHE_SECONDS:
                return self._usage_cache[1], self._usage_cache[2]
        end = self._now().astimezone(UTC)
        try:
            data, error = self.usage_reader.attempts_between(end - timedelta(days=USAGE_DAYS), end), ""
        except Exception as exc:                    # the message carries only the HTTP code, never a phone number
            data, error = None, str(exc)[:160] or type(exc).__name__
        with self._lock:
            self._usage_cache = (time.monotonic(), data, error)
        return data, error

    # -- usage: real call records only ---------------------------------------------------------------------------
    def rate(self) -> float:
        raw = self.service._get_setting("usage_sarvam_rate")
        return float(raw) if raw else DEFAULT_RATE

    def set_rate(self, value) -> dict:
        """Saves the per-minute rate of the Sarvam plan (rupees a minute)."""
        if isinstance(value, bool) or value is None:
            raise ValueError("sarvam_rate must be a number")
        try:
            n = float(value)
        except (TypeError, ValueError):
            raise ValueError("sarvam_rate must be a number") from None
        if not math.isfinite(n) or not 0 < n <= MAX_RATE:
            raise ValueError(f"sarvam_rate must be more than 0 and at most {MAX_RATE:g}")
        self.service._set_setting("usage_sarvam_rate", repr(n))
        return self.usage()

    @staticmethod
    def _totals(rows: list[dict], rate: float) -> dict:
        minutes = sum(billed_minutes(a["connectivity_status"], a["duration_in_seconds"]) for a in rows)
        pulses = sum(telephony_pulses(a["connectivity_status"], a["duration_in_seconds"]) for a in rows)
        return {"calls": len(rows), "connected": sum(1 for a in rows if a["connectivity_status"] == "connected"),
                "billed_minutes": minutes, "amount": round(minutes * rate, 2),
                "telephony_pulses": pulses, "telephony_amount": round(pulses * TELEPHONY_PULSE_RATE, 2)}

    def usage(self, refresh: bool = False) -> dict:
        rate = self.rate()
        out = {"configured": self.usage_reader is not None, "error": "", "exhausted": False, "today": None, "week": None,
               "window": None, "window_days": USAGE_DAYS, "days": [], "rate": rate, "currency": "INR",
               "note": "Minutes are counted the way Sarvam bills: started 60-second minutes of connected calls. "
                       "Calls not picked up, busy or failed cost nothing. The amount is an estimate (billed minutes "
                       "times the rate, before GST). Telephony on Sarvam's own number is Rs 0.20 per started 30-second "
                       "pulse of connected calls, also before GST. The exact figures and the credit balance are on "
                       "Sarvam's Settings, Usage and Billing pages."}
        rows, error = self._attempts(refresh)
        if rows is None:
            out["error"] = "" if error == "not configured" else error
            return out
        now = self._now().astimezone(UTC)
        today = self._now().astimezone(IST).date()
        by_day: dict[str, list[dict]] = {}
        for a in rows:
            by_day.setdefault(_when(a).astimezone(IST).date().isoformat(), []).append(a)
        out["today"] = self._totals(by_day.get(today.isoformat(), []), rate)
        out["week"] = self._totals([a for a in rows if _when(a) >= now - timedelta(days=7)], rate)
        out["window"] = self._totals(rows, rate)
        out["days"] = [{"date": d, **self._totals(by_day[d], rate)} for d in sorted(by_day, reverse=True)[:14]]
        out["exhausted"] = any(a.get("failure_reason") and _EXHAUSTED.search(a["failure_reason"])
                               and _when(a) >= now - timedelta(days=7) for a in rows)
        return out

    # -- connection checks ---------------------------------------------------------------------------------------
    def checks(self, refresh: bool = False) -> dict:
        with self._lock:
            if not refresh and self._checks_cache and time.monotonic() - self._checks_cache[0] < CACHE_SECONDS:
                return self._checks_cache[1]
        out = [self._backend(), self._database()]
        timer = self._timer()
        if timer is not None:
            out.append(timer)
        out.append(self._weather_check())
        sarvam, phone = self._sarvam_checks(refresh)
        out += [sarvam, phone]
        report = {"overall": "fail" if any(c["status"] == "fail" for c in out) else "ok",
                  "checked_at": self._now().isoformat(timespec="seconds"), "checks": out}
        with self._lock:
            self._checks_cache = (time.monotonic(), report)
        return report

    @staticmethod
    def _check(cid: str, name: str, status: str, detail: str, started: float | None = None) -> dict:
        return {"id": cid, "name": name, "status": status, "detail": detail,
                "ms": round((time.monotonic() - started) * 1000) if started is not None else None}

    def _where(self) -> str:
        """Where this backend is running: on Render (with the service name and version) or on someone's computer."""
        if self.env.get("RENDER"):
            name, commit = self.env.get("RENDER_SERVICE_NAME", ""), (self.env.get("RENDER_GIT_COMMIT") or "")[:7]
            extra = ", ".join(x for x in (name, f"version {commit}" if commit else "") if x)
            return f"Hosted on Render ({extra})" if extra else "Hosted on Render"
        return "Running on a computer, not on Render"

    def _backend(self) -> dict:
        s = self.service.status()
        live_data = (" It is using the live Supabase data." if is_postgres(self.service.db_path) and not self.env.get("RENDER")
                     else "")
        return self._check("backend", "Backend API", "ok", f"{self._where()}. Calls: {s['callMode']}. "
                           f"Daily auto-send: {'on' if s['enabled'] else 'off'}.{live_data}")

    def _timer(self) -> dict | None:
        """The Supabase wake-up timer (docs/TRIGGER.md): what it last decided. Only when the data is in Postgres."""
        if not is_postgres(self.service.db_path):
            return None
        t = time.monotonic()
        name = "Wake-up timer (Supabase)"
        try:
            with self.service.lock:
                row = self.service.db.execute("SELECT at, reason, note FROM wake_log ORDER BY id DESC LIMIT 1").fetchone()
        except OperationalError:
            return self._check("timer", name, "off", "Not set up in Supabase (see docs/TRIGGER.md).", t)
        if row is None:
            return self._check("timer", name, "ok", "Installed. No wake-up has been needed yet.", t)
        at, reason, note = row
        when = at.astimezone(IST)
        label = f"{when:%d %b %H:%M}"
        recent = self._now().astimezone(IST) - when < timedelta(hours=6)
        if note and str(note).startswith("not configured"):
            if recent:
                return self._check("timer", name, "fail", f"At {label} the backend had to be woken ({reason}) but the Supabase "
                                   "Vault secrets (backend address and token) are missing. See docs/TRIGGER.md.", t)
            return self._check("timer", name, "off", f"No recent wake-up (last attempt {label} had no Vault secrets).", t)
        return self._check("timer", name, "ok", f"Last wake-up {label} ({reason}).", t)

    def _database(self) -> dict:
        t = time.monotonic()
        try:
            with self.service.lock:
                farmers = self.service.db.execute("SELECT COUNT(*) FROM dash_farmers").fetchone()[0]
                calls = self.service.db.execute("SELECT COUNT(*) FROM dash_results").fetchone()[0]
                try:
                    saved = self.service.db.execute("SELECT COUNT(*) FROM weather").fetchone()[0]
                except Exception:
                    saved = 0
            kind = "Postgres (Supabase)" if is_postgres(self.service.db_path) else "SQLite file"
            return self._check("database", "Database", "ok",
                               f"{kind}: {farmers} farmers, {calls} call records, {saved} saved forecast days.", t)
        except Exception as exc:
            return self._check("database", "Database", "fail", f"Cannot read the database ({type(exc).__name__}).", t)

    def _weather_check(self) -> dict:
        """Never asks the weather service: weather is fetched only when a call is made, so this reads what the last call saved."""
        t = time.monotonic()
        name = f"Weather API ({getattr(self.weather, 'label', 'Open-Meteo')})"
        if getattr(self.weather, "label", "") == "WeatherAPI.com" and not getattr(self.weather, "uses_key", False):
            return self._check("weather", name, "fail", "No API key. Add WEATHERAPI_KEY (a free key from weatherapi.com).", t)
        try:
            with self.service.lock:
                last, days = self.service.db.execute("SELECT MAX(fetched_at), COUNT(*) FROM weather").fetchone()
        except Exception:
            last, days = None, 0
        if not last:
            return self._check("weather", name, "off", "Ready. Weather is fetched only when a call is made, and none has been yet.", t)
        when = datetime.fromisoformat(str(last)[:19])
        label = f"{when.day} {when:%b %H:%M}"
        return self._check("weather", name, "ok", f"Last fetched {label} for a call; {days} forecast days saved. "
                           "This page never asks the weather service.", t)

    def _sarvam_checks(self, refresh: bool) -> tuple[dict, dict]:
        if self.usage_reader is None:
            return (self._check("sarvam", "Sarvam", "off", "Not set up. The backend is in simulated mode."),
                    self._check("phone", "Phone line", "off", "Needs Sarvam to be set up first."))
        t = time.monotonic()
        rows, error = self._attempts(True if refresh else False)
        if rows is None:
            return (self._check("sarvam", "Sarvam", "fail", f"Request failed: {error}", t),
                    self._check("phone", "Phone line", "off", "Cannot be judged while Sarvam fails."))
        version = getattr(self.usage_reader, "app_version", "?")
        sarvam = self._check("sarvam", "Sarvam", "ok", f"Key accepted. Agent version {version} configured.", t)
        cutoff = self._now().astimezone(UTC) - timedelta(hours=24)
        recent = sorted((a for a in rows if _when(a) >= cutoff), key=_when)
        if not recent:
            return sarvam, self._check("phone", "Phone line", "off", "No call in the last 24 hours to judge by.")
        last = recent[-1]
        ago = max(int((self._now().astimezone(UTC) - _when(last)).total_seconds() // 60), 0)
        status = last["connectivity_status"]
        if status == "failed":
            return sarvam, self._check("phone", "Phone line", "fail",
                                       f"Last call failed {ago} min ago: {_reason_text(last.get('failure_reason') or '')}")
        word = "connected" if status == "connected" else "rang but was not picked up"
        return sarvam, self._check("phone", "Phone line", "ok", f"Last call {word} {ago} min ago.")
