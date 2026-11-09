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
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

from .adapters.open_meteo import OpenMeteoWeather
from .db import is_postgres
from .adapters.sarvam_campaign import IST, scrub
from .adapters.sarvam_usage import make_usage

UTC = timezone.utc
PROBE_PLACE = (12.97194, 77.59369)          # Bengaluru: any place will do, it only proves the weather API answers
CACHE_SECONDS = 30
DEFAULT_RATE = 3.5                          # INR a minute: Sarvam pay-as-you-go, before GST (Pro 3.25, Growth 3.15)
MAX_RATE = 1000.0
USAGE_DAYS = 60
_AUTO = object()
_EXHAUSTED = re.compile(r"insufficient[_ ]quota|\b402\b", re.I)


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
    def __init__(self, service, usage=_AUTO, weather=None, now=None):
        self.service = service
        self.usage_reader = make_usage() if usage is _AUTO else usage
        self.weather = weather or OpenMeteoWeather()
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
        return {"calls": len(rows), "connected": sum(1 for a in rows if a["connectivity_status"] == "connected"),
                "billed_minutes": minutes, "amount": round(minutes * rate, 2)}

    def usage(self, refresh: bool = False) -> dict:
        rate = self.rate()
        out = {"configured": self.usage_reader is not None, "error": "", "exhausted": False, "today": None, "week": None,
               "window": None, "window_days": USAGE_DAYS, "days": [], "rate": rate, "currency": "INR",
               "note": "Minutes are counted the way Sarvam bills: started 60-second minutes of connected calls. "
                       "Calls not picked up, busy or failed cost nothing. The amount is an estimate (billed minutes "
                       "times the rate, before GST); the exact figure and the credit balance are on Sarvam's "
                       "Settings, Usage and Billing pages."}
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
        out = [self._backend(), self._database(), self._weather_check()]
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

    def _backend(self) -> dict:
        s = self.service.status()
        return self._check("backend", "Backend API", "ok", f"Running. Calls: {s['callMode']}. "
                           f"Daily auto-send: {'on' if s['enabled'] else 'off'}.")

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
        t = time.monotonic()
        today = self._now().date()
        try:
            got = self.weather.get_forecast("probe", PROBE_PLACE[0], PROBE_PLACE[1], today)
        except Exception as exc:
            return self._check("weather", "Weather API (Open-Meteo)", "fail",
                               f"Did not answer ({type(exc).__name__}). Saved forecasts are used meanwhile.", t)
        if today not in got:
            return self._check("weather", "Weather API (Open-Meteo)", "fail", "Answered, but without today's forecast.", t)
        return self._check("weather", "Weather API (Open-Meteo)", "ok", "Answered with today's forecast.", t)

    def _sarvam_checks(self, refresh: bool) -> tuple[dict, dict]:
        if self.usage_reader is None:
            return (self._check("sarvam", "Sarvam", "off", "Not set up. The backend is in simulated mode."),
                    self._check("phone", "Phone line (Exotel)", "off", "Needs Sarvam to be set up first."))
        t = time.monotonic()
        rows, error = self._attempts(True if refresh else False)
        if rows is None:
            return (self._check("sarvam", "Sarvam", "fail", f"Request failed: {error}", t),
                    self._check("phone", "Phone line (Exotel)", "off", "Cannot be judged while Sarvam fails."))
        version = getattr(self.usage_reader, "app_version", "?")
        sarvam = self._check("sarvam", "Sarvam", "ok", f"Key accepted. Agent version {version} configured.", t)
        cutoff = self._now().astimezone(UTC) - timedelta(hours=24)
        recent = sorted((a for a in rows if _when(a) >= cutoff), key=_when)
        if not recent:
            return sarvam, self._check("phone", "Phone line (Exotel)", "off", "No call in the last 24 hours to judge by.")
        last = recent[-1]
        ago = max(int((self._now().astimezone(UTC) - _when(last)).total_seconds() // 60), 0)
        status = last["connectivity_status"]
        if status == "failed":
            return sarvam, self._check("phone", "Phone line (Exotel)", "fail",
                                       f"Last call failed {ago} min ago: {_reason_text(last.get('failure_reason') or '')}")
        word = "connected" if status == "connected" else "rang but was not picked up"
        return sarvam, self._check("phone", "Phone line (Exotel)", "ok", f"Last call {word} {ago} min ago.")
