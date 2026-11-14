"""The dashboard's backend service: import farmers, send the day's calls, keep the results, run callbacks.

It reuses the engine's checks (consent, active, phone, real weather, once per farmer per day) and the weather store
(retries, then the saved 7-day forecast). Calls go through a dialler (Sarvam or the simulated mock). Results are kept
in the same SQLite file as the call ledger, in the shape the React dashboard reads (see calls()).

Farmer phone numbers are stored here (a call needs them) but are never returned unmasked and never logged.
Callbacks: when the agent records a time the farmer asked for (`callback_time`), one call is placed at that time, inside
the calling window (5:00 to 22:00 IST), at most 30 minutes late, and never retried.
"""
from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import threading
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Callable

from .adapters.dialers import OUTPUT_VARS, make_dialler
from .adapters.local import SQLiteLedger
from .adapters.mock import MockVoice, MockWeather
from .adapters.weatherapi import geocode, make_weather
from .adapters.sarvam_agent import _LANG_NAMES
from .adapters.sarvam_campaign import IST, scrub
from .adapters.sheet import _ALIASES, _LANG, _key, _read_rows, load_farmers
from .adapters.weather_store import StoredWeather
from .config import Settings
from .db import IntegrityError, OperationalError, connect, table_columns
from .contracts import (AttemptStatus, CallAttempt, CallRequest, FarmerContext, FarmerDayResult, Language,
                        ProviderCallResult)
from .engine import Ports, final_result, prepare_call
from .script import format_now, weather_variables

CALL_FROM, CALL_TO = dtime(5, 0), dtime(22, 0)   # callbacks only inside these hours (IST), set by the team on 5 Nov
GRACE_MINUTES = 30        # a callback not placed within this long after its time is marked missed, not called late
MAX_RELATIVE_MINUTES = 12 * 60
NETWORK_DROP = "network_drop"   # set by the Sarvam adapter when a connected call was cut by the network
LIVE_STALE_MINUTES = 20      # an In Queue or In Call row older than this belongs to a process that stopped: it is dropped
INTERRUPTED_MINUTES = 10     # a retry or callback still 'calling' after this long means the process stopped mid-call
MAX_FREE_RETRIES = 2        # a dropped call (network) is retried twice a day without counting as an attempt
NETWORK_RETRY_MIN = 5
MAX_RESCHEDULES = 2       # a farmer may move a callback at most twice (team, 5 Nov)
ALREADY_NOTE = "Send skipped: already called today (one call per farmer per day)"
DAILY_RUN_TIME = dtime(9, 0)
RETRY_GAPS_MIN = (30, 60)        # client rule: 30 min before attempt 2, then 1 hour before attempt 3 (3 attempts)
FAILURE_RETRY_GAPS_MIN = (30,)   # a provider or number failure is retried once, then shown to the team

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dash_farmers(
  farmer_id TEXT PRIMARY KEY, name TEXT, phone TEXT, language TEXT, village TEXT, district TEXT, state TEXT,
  lat REAL, lon REAL, consent INT, active INT);
CREATE TABLE IF NOT EXISTS dash_results(
  farmer_id TEXT, call_date TEXT, status TEXT, note TEXT, weather TEXT, attempt_id TEXT, mode TEXT, language TEXT,
  duration_s INT, call_summary TEXT, callback_time TEXT, understood_weather TEXT, stop_calls_requested TEXT,
  transcript TEXT, updated_at TEXT, PRIMARY KEY(farmer_id, call_date));
CREATE TABLE IF NOT EXISTS dash_callbacks(
  farmer_id TEXT, due_at TEXT, source_date TEXT, status TEXT, note TEXT, attempt_id TEXT, call_summary TEXT,
  understood_weather TEXT, requested_text TEXT, updated_at TEXT, reschedules INT DEFAULT 0, PRIMARY KEY(farmer_id, due_at));
CREATE TABLE IF NOT EXISTS dash_stops(farmer_id TEXT, call_date TEXT, PRIMARY KEY(farmer_id, call_date));
CREATE TABLE IF NOT EXISTS dash_declines(farmer_id TEXT, call_date TEXT, PRIMARY KEY(farmer_id, call_date));
CREATE TABLE IF NOT EXISTS dash_tests(
  id INTEGER PRIMARY KEY AUTOINCREMENT, farmer_id TEXT, at TEXT, status TEXT, note TEXT, weather TEXT, attempt_id TEXT,
  language TEXT, duration_s INT, call_summary TEXT, callback_time TEXT, understood_weather TEXT, stop_calls_requested TEXT,
  transcript TEXT);
CREATE TABLE IF NOT EXISTS dash_paused(farmer_id TEXT PRIMARY KEY, since TEXT);
CREATE TABLE IF NOT EXISTS dash_alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, farmer_id TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS dash_retries(
  farmer_id TEXT, call_date TEXT, attempt_no INT, due_at TEXT, status TEXT, note TEXT,
  PRIMARY KEY(farmer_id, call_date, attempt_no));
-- a call that is waiting or on the phone right now (one row per farmer); the result replaces it when the call ends
CREATE TABLE IF NOT EXISTS dash_live(
  farmer_id TEXT PRIMARY KEY, call_date TEXT, kind TEXT, attempt_no INT, state TEXT, since TEXT);
CREATE TABLE IF NOT EXISTS dash_settings(key TEXT PRIMARY KEY, value TEXT);
"""

_LANG_LABELS = {Language.HI: "Hindi", Language.KN: "Kannada", Language.TE: "Telugu", Language.EN: "English"}


# ---- callback times ------------------------------------------------------------------------------------------------
def _relative_minutes(text: str) -> int | None:
    """'in 5-10 minutes' -> 10 (the later end of a range), 'in an hour' -> 60, 'half an hour' -> 30."""
    t = text.lower()
    m = re.search(r"(\d{1,4})\s*(?:-|–|to)\s*(\d{1,4})\s*(min|hour|hr)", t)
    if m:
        n, unit = max(int(m.group(1)), int(m.group(2))), m.group(3)
    else:
        m = re.search(r"(\d{1,4})\s*(min|hour|hr)", t)
        if m:
            n, unit = int(m.group(1)), m.group(2)
        elif re.search(r"half an? hour|half hour", t):
            return 30
        elif re.search(r"\b(an|one) hour\b", t):
            return 60
        else:
            return None
    minutes = n if unit == "min" else n * 60
    return minutes if 0 < minutes <= MAX_RELATIVE_MINUTES else None


def parse_callback(text: str, now: datetime) -> datetime | None:
    """When a farmer asked to be called back, in IST: 'HH:MM', 'tomorrow HH:MM' or 'in N minutes/hours'. A clock time
    that has already passed today means tomorrow. Anything unclear gives None, so nobody is called on a guess."""
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text or "")
    if not m:
        minutes = _relative_minutes(text or "")
        return None if minutes is None else now + timedelta(minutes=minutes)
    day = now.date()
    named_tomorrow = bool(re.search(r"tomorrow|कल|ನಾಳೆ", text, re.I))
    if named_tomorrow:
        day += timedelta(days=1)
    due = datetime.combine(day, dtime(int(m.group(1)), int(m.group(2))), IST)
    if not named_tomorrow and due <= now:
        due += timedelta(days=1)
    return due


def mask_phone(phone: str) -> str:
    return "******" + (phone or "")[-4:]


class DBFarmers:
    """FarmerSource over the imported farmers: the shape a real backend adapter would have."""

    def __init__(self, db: sqlite3.Connection, lock: threading.Lock):
        self.db, self.lock = db, lock

    def list_callable_ids(self, call_date: date) -> list[str]:
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT farmer_id FROM dash_farmers WHERE farmer_id NOT IN "
                                                  "(SELECT farmer_id FROM dash_paused) ORDER BY farmer_id")]

    def get_context(self, farmer_id: str) -> FarmerContext | None:
        with self.lock:
            r = self.db.execute("SELECT farmer_id,name,phone,language,village,district,lat,lon,consent,active "
                                "FROM dash_farmers WHERE farmer_id=?", (farmer_id,)).fetchone()
        if not r:
            return None
        return FarmerContext(r[0], r[1], Language(r[3]), r[4] or r[5], r[6], r[7], bool(r[8]), bool(r[9]), phone=r[2])


class DashboardService:
    def __init__(self, db_path: str, weather=None, dialler=None, note: str = "", env: dict | None = None,
                 now: Callable[[], datetime] | None = None):
        import os
        self.db_path = db_path
        self._now = now or (lambda: datetime.now(IST))
        self.db = connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript(_SCHEMA)
        if "reschedules" not in table_columns(self.db, "dash_callbacks"):      # databases made before the reschedule limit
            self.db.execute("ALTER TABLE dash_callbacks ADD COLUMN reschedules INT DEFAULT 0")
        self.db.execute("DELETE FROM dash_live")           # nothing is in progress in a process that has just started
        self.db.commit()
        self.settings = Settings.from_env()
        self.dialler, self.note = (dialler, note) if dialler else make_dialler(env)
        e = env if env is not None else os.environ
        self.real_weather = e.get("GATE0_WEATHER", "open_meteo") != "mock"
        self._weather = weather or (make_weather(e) if self.real_weather else MockWeather())
        self.ports: Ports | None = None      # engine connections are made inside the working thread (SQLite is per thread)
        self.running = False
        self.last_run: dict | None = None
        self.cb_lock = threading.Lock()
        self._tick_lock = threading.Lock()
        self._manual: set[str] = set()          # farmers with a call placed by hand in progress

    def _make_ports(self) -> Ports:
        return Ports(DBFarmers(self.db, self.lock), SQLiteLedger(self.db_path), StoredWeather(
            self._weather, self.db_path, retry_minutes=(), sleep=lambda s: None),   # one request per place and day: the weather retries are the service's own, later
            MockVoice(), None)

    # -- settings ------------------------------------------------------------------------------------------------
    def _get_setting(self, key: str, default: str = "") -> str:
        with self.lock:
            row = self.db.execute("SELECT value FROM dash_settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _set_setting(self, key: str, value: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO dash_settings VALUES(?,?)", (key, value))
            self.db.commit()

    def auto_dispatch_enabled(self) -> bool:
        return self._get_setting("auto_dispatch", "off") == "on"     # off until someone turns it on

    def set_auto_dispatch(self, enabled: bool) -> dict:
        self._set_setting("auto_dispatch", "on" if enabled else "off")
        return self.status()

    def status(self) -> dict:
        return {"enabled": self.auto_dispatch_enabled(), "scheduledTime": "09:00 AM IST", "cronSchedule": "0 9 * * *",
                "lastRun": self._get_setting("last_auto_run") or None, "systemStatus": "Operational",
                "running": self.running, "callMode": self.dialler.mode, "live": self.dialler.live,
                "sarvamLive": self.dialler.live,
                "note": self.note, "weatherSource": f"{getattr(self._weather, 'label', 'Open-Meteo')} (real)" if self.real_weather else "mock",
                "lastSend": self.last_run}

    # -- alerts for the team, and farmers who asked us to stop -------------------------------------------------------
    def _alert(self, kind: str, fid: str, text: str) -> None:
        with self.lock:
            self.db.execute("INSERT INTO dash_alerts(at, kind, farmer_id, text) VALUES(?,?,?,?)",
                            (self._now().isoformat(timespec="seconds"), kind, fid, text))
            self.db.commit()

    def alerts(self, limit: int = 50) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT a.at, a.kind, a.farmer_id, f.name, a.text FROM dash_alerts a "
                                   "LEFT JOIN dash_farmers f ON f.farmer_id=a.farmer_id ORDER BY a.id DESC LIMIT ?",
                                   (limit,)).fetchall()
        return [{"at": r[0], "kind": r[1], "farmer_id": r[2], "farmer_name": r[3] or "", "text": r[4]} for r in rows]

    def _is_paused(self, fid: str) -> bool:
        with self.lock:
            return self.db.execute("SELECT 1 FROM dash_paused WHERE farmer_id=?", (fid,)).fetchone() is not None

    def _note_stop(self, fid: str, day: date) -> None:
        """'Stop calling me' on a second, different day stops the calls and tells a person (who updates consent)."""
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO dash_stops VALUES(?,?)", (fid, day.isoformat()))
            days = self.db.execute("SELECT COUNT(*) FROM dash_stops WHERE farmer_id=?", (fid,)).fetchone()[0]
            new = days >= 2 and self.db.execute("INSERT OR IGNORE INTO dash_paused VALUES(?,?)",
                                                (fid, self._now().isoformat(timespec="seconds"))).rowcount == 1
            self.db.commit()
        if new:
            self._alert("stop_calls", fid, "Asked to stop calling on two different days. Calls are stopped; "
                                          "please check consent with the farmer and update it.")

    def _note_decline(self, fid: str, day: date) -> None:
        """'I don't need this': no retry today, called again tomorrow. From the second day on, the team is told; calls
        stop only when the team marks the farmer as no consent."""
        with self.lock:
            new = self.db.execute("INSERT OR IGNORE INTO dash_declines VALUES(?,?)", (fid, day.isoformat())).rowcount == 1
            days = self.db.execute("SELECT COUNT(*) FROM dash_declines WHERE farmer_id=?", (fid,)).fetchone()[0]
            self.db.commit()
        if new and days >= 2:
            self._alert("declined_again", fid, f"Said they do not need the weather information on {days} different days. "
                                               "Please ask the farmer; if they do not want calls, set consent to No.")

    # -- farmers -------------------------------------------------------------------------------------------------
    def import_csv(self, text: str) -> dict:
        """Saves the farmers in a CSV or sheet export (Farmer ID, Farmer Name, Mobile Number, Village, District, State,
        Preferred Calling Language, Call Consent, optional Active, Latitude, Longitude). Same Farmer ID updates the row."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            p = Path(d) / "upload.csv"
            p.write_text(text, encoding="utf-8")
            farmers = load_farmers(p, geocode if self.real_weather else None)
            rows = _read_rows(p)
        headers = [_key(h) for h in rows[0]]
        col = {f: next((headers.index(a) for a in al if a in headers), None) for f, al in _ALIASES.items()}
        extra: dict[str, tuple[str, str, str]] = {}
        for row in rows[1:]:
            get = lambda f: str(row[col[f]]).strip() if col[f] is not None and col[f] < len(row) and row[col[f]] is not None else ""  # noqa: E731
            if get("farmer_id"):
                extra[get("farmer_id")] = (get("village"), get("district"), get("state"))
        with self.lock:
            for f in farmers:
                village, district, state = extra.get(f.farmer_id, ("", "", ""))
                self.db.execute("DELETE FROM dash_paused WHERE farmer_id=?", (f.farmer_id,))   # sheet updated by a person
                self.db.execute("INSERT OR REPLACE INTO dash_farmers VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                    f.farmer_id, f.display_name, f.phone, f.language.value, village, district, state,
                    f.latitude, f.longitude, int(f.consent), int(f.active)))
            self.db.commit()
        return {"imported": len(farmers), "no_location": [f.farmer_id for f in farmers if not (f.latitude or f.longitude)]}

    _FARMER_COLS = "farmer_id,name,phone,language,village,district,state,lat,lon,consent,active"

    @staticmethod
    def _farmer_dict(r) -> dict:
        return {"farmer_id": r[0], "farmer_name": r[1], "phone_number": mask_phone(r[2]),
                "preferred_language": _LANG_LABELS[Language(r[3])], "village": r[4], "district": r[5], "state": r[6],
                "located": bool(r[7] or r[8]), "call_consent": "Yes" if r[9] else "No", "active": "Yes" if r[10] else "No"}

    def farmers(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute(f"SELECT {self._FARMER_COLS} FROM dash_farmers ORDER BY farmer_id").fetchall()
        return [self._farmer_dict(r) for r in rows]

    # -- adding and editing farmers by hand (an admin) ---------------------------------------------------------------
    @staticmethod
    def _yes_no(value, field: str) -> bool:
        if isinstance(value, bool):
            return value
        v = str(value).strip().lower()
        if v in ("yes", "y", "true", "1"):
            return True
        if v in ("no", "n", "false", "0"):
            return False
        raise ValueError(f"{field} must be Yes or No")

    @staticmethod
    def _clean_phone(value) -> str:
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if len(digits) != 10:
            raise ValueError("phone number must have 10 digits")
        return digits

    def _next_farmer_id(self) -> str:
        with self.lock:
            ids = [r[0] for r in self.db.execute("SELECT farmer_id FROM dash_farmers")]
        top = max((int(m.group(1)) for i in ids if (m := re.fullmatch(r"F(\d+)", i))), default=0)
        return f"F{top + 1:03d}"

    def _locate(self, village: str, district: str, state: str) -> tuple[float, float]:
        if not self.real_weather:
            return 0.0, 0.0
        try:
            place = geocode(village, district, state)
        except Exception:                       # lookup down: saved without a location, so no weather and no call
            place = None
        return (place.latitude, place.longitude) if place else (0.0, 0.0)

    def add_farmer(self, data: dict) -> dict:
        """Saves one farmer typed in by an admin. Consent is never assumed: it is Yes only if the form says so."""
        name = str(data.get("farmer_name", "")).strip()
        village, district = str(data.get("village", "")).strip(), str(data.get("district", "")).strip()
        state = str(data.get("state", "")).strip()
        if not name:
            raise ValueError("farmer name is required")
        if not (village or district):
            raise ValueError("village or district is required")
        lang = _LANG.get(_key(data.get("preferred_language", "")))
        if lang is None:
            raise ValueError("language must be Hindi, Kannada, Telugu or English")
        phone = self._clean_phone(data.get("phone_number"))
        fid = str(data.get("farmer_id") or "").strip() or self._next_farmer_id()
        with self.lock:
            if self.db.execute("SELECT 1 FROM dash_farmers WHERE farmer_id=?", (fid,)).fetchone():
                raise ValueError(f"Farmer ID {fid} already exists")
        lat, lon = self._locate(village, district, state)
        consent = self._yes_no(data.get("call_consent", False), "call consent")
        active = self._yes_no(data.get("active", True), "active")
        with self.lock:
            self.db.execute("INSERT INTO dash_farmers VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                fid, name[:80], phone, lang.value, village, district, state, lat, lon, int(consent), int(active)))
            self.db.commit()
        return next(f for f in self.farmers() if f["farmer_id"] == fid)

    def update_farmer(self, fid: str, data: dict) -> dict:
        """Changes only the fields sent (name, phone, language, place, consent, active). A blank phone keeps the old one."""
        with self.lock:
            r = self.db.execute(f"SELECT {self._FARMER_COLS} FROM dash_farmers WHERE farmer_id=?", (fid,)).fetchone()
        if not r:
            raise KeyError(fid)
        _, name, phone, language, village, district, state, lat, lon, consent, active = r
        if "farmer_name" in data:
            name = str(data["farmer_name"]).strip()
            if not name:
                raise ValueError("farmer name is required")
        if str(data.get("phone_number") or "").strip():
            phone = self._clean_phone(data["phone_number"])
        if "preferred_language" in data:
            lang = _LANG.get(_key(data["preferred_language"]))
            if lang is None:
                raise ValueError("language must be Hindi, Kannada, Telugu or English")
            language = lang.value
        moved = False
        for key in ("village", "district", "state"):
            if key in data and str(data[key]).strip() != {"village": village, "district": district, "state": state}[key]:
                moved = True
        if "village" in data:
            village = str(data["village"]).strip()
        if "district" in data:
            district = str(data["district"]).strip()
        if "state" in data:
            state = str(data["state"]).strip()
        if not (village or district):
            raise ValueError("village or district is required")
        if moved or not (lat or lon):
            lat, lon = self._locate(village, district, state)       # the place changed, or it was never found: look it up again
        if "call_consent" in data:
            consent = int(self._yes_no(data["call_consent"], "call consent"))
        if "active" in data:
            active = int(self._yes_no(data["active"], "active"))
        with self.lock:
            self.db.execute("UPDATE dash_farmers SET name=?, phone=?, language=?, village=?, district=?, state=?, lat=?, "
                            "lon=?, consent=?, active=? WHERE farmer_id=?",
                            (name[:80], phone, language, village, district, state, lat, lon, consent, active, fid))
            self.db.commit()
        return next(f for f in self.farmers() if f["farmer_id"] == fid)

    # -- calls in progress: shown on the call log from the moment they are triggered --------------------------------
    def _live_set(self, fid: str, day: date, kind: str, attempt: int, state: str) -> None:
        """Marks the farmer In Queue ('queued') or In Call ('calling') on the call log. Never raises: showing a call must
        never stop one."""
        try:
            with self.lock:
                self.db.execute("INSERT OR REPLACE INTO dash_live VALUES(?,?,?,?,?,?)",
                                (fid, day.isoformat(), kind, attempt, state, self._now().isoformat(timespec="seconds")))
                self.db.commit()
        except Exception:
            pass

    def _live_clear(self, fid: str) -> None:
        try:
            with self.lock:
                self.db.execute("DELETE FROM dash_live WHERE farmer_id=?", (fid,))
                self.db.commit()
        except Exception:
            pass

    def _live_rows(self) -> list[tuple]:
        """(farmer, day, kind, attempt, state, since) of calls waiting or on the phone, without the stale ones."""
        with self.lock:
            try:
                rows = self.db.execute("SELECT farmer_id, call_date, kind, attempt_no, state, since FROM dash_live").fetchall()
            except OperationalError:
                return []
        keep, now = [], self._now()
        for r in rows:
            try:
                fresh = now - datetime.fromisoformat(r[5]) <= timedelta(minutes=LIVE_STALE_MINUTES)
            except (TypeError, ValueError):
                fresh = False
            if fresh:
                keep.append(r)
            else:
                self._live_clear(r[0])
        return keep

    def _live_label(self, lv: tuple) -> tuple[str, str]:
        """The dashboard's status and disposition for a call that is waiting or on the phone."""
        _, _, kind, attempt, state, _ = lv
        what = {"retry": f"attempt {attempt} of {self.settings.max_attempts}", "callback": "callback", "test": "test call",
                "manual": "call placed by hand"}.get(kind, "today's call")
        if state == "calling":
            return "In Call", f"Calling now ({what})"
        return "In Queue", f"Waiting in the queue ({what})"

    def _live_row(self, lv: tuple) -> dict:
        """A call log row for a call that has no result yet (its first call of the day, a test, or a callback)."""
        fid, day, kind, attempt, state, since = lv
        with self.lock:
            f = self.db.execute("SELECT name, phone, language, village, district FROM dash_farmers WHERE farmer_id=?", (fid,)).fetchone()
        name, phone, lang, village, district = f or (None, "", "", "", "")
        status, disposition = self._live_label(lv)
        test = kind == "test"
        return {
            "call_id": f"TEST-LIVE-{fid}" if test else f"{fid}-{day}", "is_test": test, "live": True, "farmer_id": fid,
            "farmer_name": name or f"Farmer {fid}", "phone_number": mask_phone(phone or ""),
            "location": ", ".join(x for x in (village, district) if x), "village": village or "", "district": district or "",
            "call_date": day, "created_at": since, "language": _LANG_LABELS[Language(lang)] if lang else "",
            "weather_temp": None, "weather_windspeed": None, "weather_rainfall": None, "weather_humidity": None,
            "weather_source": "", "status": status, "disposition": f"Test call: {disposition}" if test else disposition,
            "note": "", "retry_count": 0, "duration_seconds": 0, "attempts_used": 0, "max_attempts": self.settings.max_attempts,
            "next_attempt_at": None, "scheduled_callback_time": None, "callback_status": None, "callback_requested_text": "",
            "summary": "", "understood_weather": "", "stop_calls_requested": "", "transcript": [], "attempts_log": [],
            "call_mode": self.dialler.mode, "attempt_id": ""}

    # -- sending the day's calls ---------------------------------------------------------------------------------
    def _save(self, fid: str, day: date, **kw) -> None:
        cols = ["status", "note", "weather", "attempt_id", "mode", "language", "duration_s", *OUTPUT_VARS, "transcript"]
        vals = [kw.get(c) if c == "duration_s" else kw.get(c, "") for c in cols]      # a number column gets a number or NULL
        with self.lock:
            self.db.execute(f"INSERT OR REPLACE INTO dash_results VALUES(?,?,{','.join('?' * len(cols))},?)",
                            (fid, day.isoformat(), *vals, self._now().isoformat(timespec="seconds")))
            self.db.commit()

    def _variables(self, farmer: FarmerContext, w) -> dict:
        # only variables the agent declares (Sarvam returns 422 otherwise); now_text lets it confirm callback days
        return weather_variables(farmer, w, format_now(self._now()))

    def fire_one(self, fid: str, day: date, kind: str = "daily") -> str:
        prepared = prepare_call(CallRequest(fid, day), self.ports, self.settings)
        if isinstance(prepared, FarmerDayResult):
            reason = prepared.skip_reason.value if prepared.skip_reason else prepared.result.value
            if reason == "already_called_today":           # keep the earlier real result, just say why nothing new happened
                with self.lock:
                    row = self.db.execute("SELECT status, note FROM dash_results WHERE farmer_id=? AND call_date=?",
                                          (fid, day.isoformat())).fetchone()
                    if row and row[0] == "skipped":         # skipped earlier: keep its own reason (no consent, ...)
                        return row[1] or reason
                    if row and row[0] in ("failed", "error"):   # keep the real failure reason, do not bury it
                        return reason
                    self.db.execute("UPDATE dash_results SET note=? WHERE farmer_id=? AND call_date=?",
                                    (ALREADY_NOTE, fid, day.isoformat()))
                    self.db.commit()
            else:
                self._save(fid, day, status="skipped", note=reason, mode=self.dialler.mode)
                if reason == "weather_unavailable":
                    self._alert("weather_unavailable", fid, "No weather for this farmer today, so no call was made.")
            return reason
        farmer, w = prepared.farmer, prepared.weather
        self._live_set(fid, day, kind, 1, "calling")
        res, out = self._place(farmer, w)
        self.ports.ledger.record_attempt(CallAttempt(
            farmer_id=fid, call_date=day, attempt_no=1, status=res.status, language=farmer.language,
            message_text=prepared.message, provider_call_id=res.provider_call_id, duration_s=res.duration_s,
            error=res.error, weather_source=w.source))
        self.ports.ledger.record_day_result(FarmerDayResult(fid, day, final_result(res.status), 1))
        self._store_outcome(fid, day, farmer, w, 1, res, out)
        return "called"

    def _place(self, farmer: FarmerContext, w) -> tuple[ProviderCallResult, dict]:
        """One call and, if it was answered, what the agent recorded. Provider errors never stop the run (type only)."""
        try:
            res = self.dialler.place(farmer.phone, _LANG_NAMES[farmer.language], self._variables(farmer, w))
        except Exception as exc:
            res = ProviderCallResult(AttemptStatus.FAILED, error=type(exc).__name__)
        out: dict = {}
        if res.status is AttemptStatus.ANSWERED:
            try:
                out = self.dialler.outputs(res.provider_call_id)
            except Exception:
                out = {}
        return res, out

    def _store_outcome(self, fid: str, day: date, farmer: FarmerContext, w, attempt_no: int,
                       res: ProviderCallResult, out: dict, at: datetime | None = None, weather: dict | None = None) -> None:
        """Keeps the latest attempt's result for the dashboard, then plans a callback or a retry if one is due.
        at: when the call ended, if that is not now (a result recovered after an interruption); times such as 'in 5
        minutes' and the next retry are counted from it."""
        if weather is None:
            weather = ({"temp_min": w.temp_min_c, "temp_max": w.temp_max_c, "wind": w.wind_kmh, "rain": w.rain_chance_pct,
                        "humidity": w.humidity_pct, "source": w.source} if w is not None else {})
        transcript = [{"speaker": m["speaker"], "text": scrub(m["text"])} for m in out.pop("transcript", None) or []]
        if out.get("call_summary"):
            out["call_summary"] = scrub(out["call_summary"])            # free text: phone-like numbers masked
        self._save(fid, day, status=res.status.value, note=res.error, weather=json.dumps(weather),
                   attempt_id=res.provider_call_id, mode=self.dialler.mode, language=farmer.language.value,
                   duration_s=res.duration_s, transcript=json.dumps(transcript) if transcript else "", **out)
        if out.get("stop_calls_requested") == "yes":
            self._note_stop(fid, day)
        if out.get("understood_weather") == "declined":
            self._note_decline(fid, day)
        if out.get("callback_time") and out.get("stop_calls_requested") != "yes":
            self._schedule_callback(fid, day, out["callback_time"], now=at)
        if not self._plan_retry(fid, day, attempt_no, res.status, out, res.error, at) and res.status is AttemptStatus.FAILED:
            self._alert("provider_failure", fid,
                        f"The call failed and will not be retried ({scrub(res.error or 'provider error')[:80]}).")

    # -- retries: 3 attempts, 30 min then 1 hour; a farmer who asked for a callback or to stop is not retried ----------
    def _has_callback(self, fid: str, day: date) -> bool:
        with self.lock:
            return self.db.execute("SELECT 1 FROM dash_callbacks WHERE farmer_id=? AND source_date=?",
                                   (fid, day.isoformat())).fetchone() is not None

    def _attempt_errors(self, fid: str, day: date) -> list[str]:
        """The error text of each attempt recorded for that farmer and day, in order."""
        with self.lock:
            try:
                rows = self.db.execute("SELECT error FROM attempts WHERE farmer_id=? AND call_date=? ORDER BY attempt_no",
                                       (fid, day.isoformat())).fetchall()
            except OperationalError:
                return []
        return [r[0] or "" for r in rows]

    def _plan_retry(self, fid: str, day: date, attempt_no: int, status: AttemptStatus, out: dict, error: str = "",
                    at: datetime | None = None) -> bool:
        """Plans the next call; False when none is due (so the caller can alert on a failed call). attempt_no is the
        call's place in the day's sequence; the first MAX_FREE_RETRIES network drops do not count as attempts."""
        understood = out.get("understood_weather")
        if self._has_callback(fid, day) or out.get("stop_calls_requested") == "yes" or understood == "declined":
            return False                       # a callback, a stop request or 'I don't need this': no retry today
        errors = self._attempt_errors(fid, day)
        total = max(len(errors), attempt_no)
        drops = sum(1 for e in errors if e == NETWORK_DROP)
        counted = total - min(drops, MAX_FREE_RETRIES)
        free = error == NETWORK_DROP and drops <= MAX_FREE_RETRIES
        if free:
            minutes = NETWORK_RETRY_MIN        # the farmer was cut off: ring again soon, attempt count unchanged
        else:
            if error == NETWORK_DROP or status in (AttemptStatus.NO_ANSWER, AttemptStatus.BUSY) or (
                    status is AttemptStatus.ANSWERED and understood in ("no", "unclear", "no_response")):
                gaps = RETRY_GAPS_MIN          # not picked up, rejected, busy, silent, or heard but never confirmed
            elif status is AttemptStatus.FAILED:
                gaps = FAILURE_RETRY_GAPS_MIN
            else:
                return False
            if counted >= self.settings.max_attempts or counted > len(gaps):
                return False
            minutes = gaps[counted - 1]
        due = (at or self._now()) + timedelta(minutes=minutes)
        if due.date() != day or not (CALL_FROM <= due.timetz().replace(tzinfo=None) <= CALL_TO):
            return False                       # a retry never runs after the calling window or on another day
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO dash_retries VALUES(?,?,?,?,?,?)", (
                fid, day.isoformat(), total + 1, due.isoformat(timespec="seconds"), "pending", ""))
            self.db.commit()
        return True

    def _retry_update(self, fid: str, day: str, attempt_no: int, status: str, note: str = "") -> None:
        with self.lock:
            self.db.execute("UPDATE dash_retries SET status=?, note=? WHERE farmer_id=? AND call_date=? AND attempt_no=?",
                            (status, note, fid, day, attempt_no))
            self.db.commit()

    def run_due_retries(self, now: datetime | None = None) -> int:
        """Places the retries whose time has come. A retry the system missed by more than 30 minutes is dropped, not
        placed late. Consent, active status and weather are checked again first. Returns how many calls were placed."""
        now = now or self._now()
        placed = 0
        with self.cb_lock:
            with self.lock:
                due = self.db.execute("SELECT farmer_id, call_date, attempt_no, due_at FROM dash_retries "
                                      "WHERE status='pending' AND due_at<=? ORDER BY due_at",
                                      (now.isoformat(timespec="seconds"),)).fetchall()
            if not due:
                return 0
            ports = self._make_ports()
            for fid, day, attempt_no, due_at in due:
                if datetime.fromisoformat(due_at) >= now - timedelta(minutes=GRACE_MINUTES):
                    self._live_set(fid, date.fromisoformat(day), "retry", attempt_no, "queued")
            for fid, day, attempt_no, due_at in due:
                if datetime.fromisoformat(due_at) < now - timedelta(minutes=GRACE_MINUTES):
                    self._retry_update(fid, day, attempt_no, "missed", f"not placed within {GRACE_MINUTES} min")
                    continue
                self._retry_update(fid, day, attempt_no, "calling", now.isoformat(timespec="seconds"))   # claimed at
                try:
                    outcome = self._retry_one(ports, fid, date.fromisoformat(day), attempt_no)
                except Exception as exc:
                    outcome = f"error: {type(exc).__name__}"
                finally:
                    self._live_clear(fid)
                self._retry_update(fid, day, attempt_no, "done" if outcome == "placed" else "dropped", "" if outcome == "placed" else outcome)
                placed += outcome == "placed"
        return placed

    def _retry_one(self, ports: Ports, fid: str, day: date, attempt_no: int) -> str:
        farmer = ports.farmers.get_context(fid)
        if farmer is None or not farmer.active or not farmer.consent or not farmer.phone or self._is_paused(fid):
            return "not callable (consent, active, phone or asked to stop)"
        w = ports.weather.get_weather(farmer.place_name, farmer.latitude, farmer.longitude, day)
        if w is None:
            return "weather_unavailable"
        self._live_set(fid, day, "retry", attempt_no, "calling")
        res, out = self._place(farmer, w)
        try:
            ports.ledger.record_attempt(CallAttempt(
                farmer_id=fid, call_date=day, attempt_no=attempt_no, status=res.status, language=farmer.language,
                message_text="(retry)", provider_call_id=res.provider_call_id, duration_s=res.duration_s,
                error=res.error, weather_source=w.source))
        except IntegrityError:
            ports.ledger.db.rollback()          # a failed insert must not keep the database locked
        ports.ledger.db.execute("UPDATE day_results SET result=?, attempts=? WHERE farmer_id=? AND call_date=?",
                                (final_result(res.status).value, attempt_no, fid, day.isoformat()))
        ports.ledger.db.commit()
        self._store_outcome(fid, day, farmer, w, attempt_no, res, out)
        return "placed"

    def fire(self, day: date) -> None:
        self.running = True
        try:
            self.ports = self._make_ports()
            counts: dict[str, int] = {}
            ids = self.ports.farmers.list_callable_ids(day)
            for fid in ids:                                 # everyone waiting shows as In Queue from the start
                self._live_set(fid, day, "daily", 1, "queued")
            for fid in ids:
                try:
                    outcome = self.fire_one(fid, day)
                except Exception as exc:                    # one farmer never stops the others
                    self._save(fid, day, status="error", note=type(exc).__name__, mode=self.dialler.mode)
                    outcome = "error"
                finally:
                    self._live_clear(fid)
                counts[outcome] = counts.get(outcome, 0) + 1
            self.last_run = {"date": day.isoformat(), "counts": counts, "at": self._now().strftime("%H:%M:%S")}
        finally:
            self.running = False

    def start_fire(self, day: date) -> bool:
        """Runs fire() in the background; False if a run is already going."""
        if self.running:
            return False
        threading.Thread(target=self.fire, args=(day,), daemon=True).start()
        return True

    # -- the Call button on a farmer card ------------------------------------------------------------------------------
    def manual_call(self, fid: str, mode: str = "retry") -> dict:
        """Places a call now for one farmer, by hand.

        mode "retry" follows the retry rules: with no result yet today it is the day's first call; with a result that is
        still retryable it is the next attempt (the attempt count goes up by one and the waiting retry is replaced). It is
        refused, with the reason, when the farmer is completed, declined, has a callback booked, has used all attempts,
        is inactive, has no consent, asked to stop, or when it is outside the calling hours.

        mode "test" ignores the retry rules: the call is kept as its own Test row and never changes the farmer's real
        result, attempt count, retries, callbacks or alerts, and it can be repeated. Consent, active, phone, a stop
        request and the calling hours still apply."""
        if mode not in ("retry", "test"):
            raise ValueError('mode must be "retry" or "test"')
        now = self._now()
        day = now.date()
        with self.lock:
            r = self.db.execute("SELECT active, consent, phone FROM dash_farmers WHERE farmer_id=?", (fid,)).fetchone()
        if not r:
            raise KeyError(fid)
        if not r[0]:
            raise ValueError("this farmer is inactive")
        if not r[1]:
            raise ValueError("this farmer has not given call consent")
        if not r[2]:
            raise ValueError("this farmer has no phone number")
        if self._is_paused(fid):
            raise ValueError("calls are stopped for this farmer: they asked us to stop")
        if not (CALL_FROM <= now.timetz().replace(tzinfo=None) <= CALL_TO):
            raise ValueError("calls can only be placed between 05:00 and 22:00 India time")
        if mode == "retry" and self.running:
            raise ValueError("today's send is running; try again when it finishes")
        kind, seq, attempt = "first", 1, 1
        with self.lock:
            if fid in self._manual:
                raise ValueError("a call to this farmer is already in progress")
            row = None if mode == "test" else self.db.execute(
                "SELECT status, note, understood_weather, stop_calls_requested FROM dash_results "
                "WHERE farmer_id=? AND call_date=?", (fid, day.isoformat())).fetchone()
        if row:
            status, note, understood, stop = row
            understood = understood or ""
            if self._has_callback(fid, day):
                raise ValueError("a callback is already booked for this farmer")
            if stop == "yes":
                raise ValueError("this farmer asked to stop the calls")
            if understood == "yes":
                raise ValueError("already completed today: the farmer understood the weather")
            if understood == "declined":
                raise ValueError("the farmer said they do not need the weather today")
            if status == "skipped":
                raise ValueError(f"skipped today ({(note or 'no reason').replace('_', ' ')})")
            errors = self._attempt_errors(fid, day)
            drops = sum(1 for e in errors if e == NETWORK_DROP)
            counted = len(errors) - min(drops, MAX_FREE_RETRIES)
            if counted >= self.settings.max_attempts:
                raise ValueError(f"all {self.settings.max_attempts} attempts are used today")
            kind, seq, attempt = "retry", len(errors) + 1, counted + 1
        with self.lock:
            self._manual.add(fid)
        self._live_set(fid, day, "test" if mode == "test" else "manual", attempt, "queued")

        def work():
            try:
                if mode == "test":
                    self._test_call(fid)
                    return
                with self.cb_lock:
                    ports = self._make_ports()
                    if kind == "first":
                        self.ports = ports
                        self.fire_one(fid, day, "manual")
                    else:
                        with self.lock:
                            self.db.execute("UPDATE dash_retries SET status='superseded', note='called by hand' "
                                            "WHERE farmer_id=? AND call_date=? AND status='pending'", (fid, day.isoformat()))
                            self.db.commit()
                        self._retry_one(ports, fid, day, seq)
            except Exception:
                pass
            finally:
                self._live_clear(fid)
                with self.lock:
                    self._manual.discard(fid)
        threading.Thread(target=work, daemon=True).start()
        if mode == "test":
            return {"started": True, "kind": "test", "attempt": None, "max_attempts": self.settings.max_attempts}
        return {"started": True, "kind": kind, "attempt": attempt, "max_attempts": self.settings.max_attempts}

    def _test_call(self, fid: str) -> None:
        """One test call, kept as its own row. Nothing here touches the day's result, attempts, retries or callbacks."""
        ports = self._make_ports()
        farmer = ports.farmers.get_context(fid)
        w = ports.weather.get_weather(farmer.place_name, farmer.latitude, farmer.longitude, self._now().date())
        stamp = self._now().isoformat(timespec="seconds")
        if w is None:
            self._save_test(fid, stamp, "skipped", "weather_unavailable", {}, "", farmer.language.value, 0, {})
            return
        self._live_set(fid, self._now().date(), "test", 1, "calling")
        try:
            res, out = self._place(farmer, w)
            weather = {"temp_min": w.temp_min_c, "temp_max": w.temp_max_c, "wind": w.wind_kmh, "rain": w.rain_chance_pct,
                       "humidity": w.humidity_pct, "source": w.source}
            self._save_test(fid, stamp, res.status.value, res.error, weather, res.provider_call_id, farmer.language.value,
                            res.duration_s or 0, out)
        finally:
            self._live_clear(fid)                           # the saved Test row replaces the In Call row

    def _save_test(self, fid, stamp, status, note, weather, attempt_id, language, duration, out) -> None:
        transcript = [{"speaker": m["speaker"], "text": scrub(m["text"])} for m in out.pop("transcript", None) or []]
        with self.lock:
            self.db.execute(
                "INSERT INTO dash_tests(farmer_id, at, status, note, weather, attempt_id, language, duration_s, call_summary, "
                "callback_time, understood_weather, stop_calls_requested, transcript) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, stamp, status, scrub(note or ""), json.dumps(weather) if weather else "", attempt_id, language, duration,
                 scrub(out.get("call_summary", "")), out.get("callback_time", ""), out.get("understood_weather", ""),
                 out.get("stop_calls_requested", ""), json.dumps(transcript) if transcript else ""))
            self.db.commit()

    def _test_rows(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT t.id, t.farmer_id, t.at, t.status, t.note, t.weather, t.attempt_id, t.language, t.duration_s, "
                "t.call_summary, t.callback_time, t.understood_weather, t.stop_calls_requested, t.transcript, "
                "f.name, f.phone, f.village, f.district FROM dash_tests t LEFT JOIN dash_farmers f ON f.farmer_id=t.farmer_id "
                "ORDER BY t.id DESC LIMIT 200").fetchall()
        label = {"answered": "Answered", "no_answer": "No Answer or Rejected", "busy": "Busy", "failed": "Failed"}
        out = []
        for (tid, fid, at, status, note, weather, attempt_id, lang, dur, summary, cb, understood, stop, transcript,
             name, phone, village, district) in rows:
            dash_status, disposition = self._status_for(status, understood or "", False, False)
            if status == "skipped":
                disposition = (note or "skipped").replace("_", " ").title()
            w = json.loads(weather) if weather else {}
            out.append({
                "call_id": f"TEST{tid}-{fid}", "is_test": True, "farmer_id": fid, "farmer_name": name or f"Farmer {fid}",
                "phone_number": mask_phone(phone or ""), "location": ", ".join(x for x in (village, district) if x),
                "village": village or "", "district": district or "", "call_date": at[:10], "created_at": at,
                "language": _LANG_LABELS[Language(lang)] if lang else "",
                "weather_temp": f"{w['temp_min']}-{w['temp_max']}" if w else None,
                "weather_windspeed": w.get("wind"), "weather_rainfall": w.get("rain"), "weather_humidity": w.get("humidity"),
                "weather_source": w.get("source", ""), "status": dash_status, "disposition": f"Test call: {disposition}",
                "note": scrub(note or ""), "retry_count": 0, "duration_seconds": dur or 0, "attempts_used": 0,
                "max_attempts": self.settings.max_attempts, "next_attempt_at": None, "scheduled_callback_time": None,
                "callback_status": None, "callback_requested_text": cb or "", "summary": summary or "",
                "understood_weather": understood or "", "stop_calls_requested": stop or "",
                "transcript": json.loads(transcript) if transcript else [],
                "attempts_log": [{"attempt_number": 1, "status": label.get(status, status), "duration_seconds": dur or 0,
                                  "error_message": scrub(note or "")}] if status != "skipped" else [],
                "call_mode": self.dialler.mode, "attempt_id": attempt_id or ""})
        return out

    # -- callbacks: one more call at the time the farmer asked for, never retried ---------------------------------
    def _schedule_callback(self, fid: str, source_day: date, text: str, now: datetime | None = None,
                           reschedules: int = 0) -> None:
        due = parse_callback(text, now or self._now())
        if due is None:
            return
        in_hours = CALL_FROM <= due.timetz().replace(tzinfo=None) <= CALL_TO
        status, note = ("pending", "") if in_hours else ("skipped", "outside calling hours (5:00 to 22:00 IST)")
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO dash_callbacks(farmer_id, due_at, source_date, status, note, attempt_id, "
                            "call_summary, understood_weather, requested_text, updated_at, reschedules) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                fid, due.isoformat(timespec="seconds"), source_day.isoformat(), status, note, "", "", "",
                scrub(text)[:60], self._now().isoformat(timespec="seconds"), reschedules))
            self.db.commit()

    def _cb_update(self, fid: str, due_at: str, **kw) -> None:
        sets = ", ".join(f"{k}=?" for k in kw)
        with self.lock:
            self.db.execute(f"UPDATE dash_callbacks SET {sets}, updated_at=? WHERE farmer_id=? AND due_at=?",
                            (*kw.values(), self._now().isoformat(timespec="seconds"), fid, due_at))
            self.db.commit()

    def run_due_callbacks(self, now: datetime | None = None) -> int:
        """Places the callbacks whose time has come. Each gets exactly one attempt and is closed afterwards (no retry).
        Consent, active status and weather are checked again first. Returns how many calls were placed."""
        now = now or self._now()
        placed = 0
        with self.cb_lock:
            with self.lock:
                due = self.db.execute("SELECT farmer_id, due_at, source_date FROM dash_callbacks WHERE status='pending' "
                                      "AND due_at<=? ORDER BY due_at", (now.isoformat(timespec="seconds"),)).fetchall()
            if not due:
                return 0
            ports = self._make_ports()
            for fid, due_at, source_date in due:
                if datetime.fromisoformat(due_at) >= now - timedelta(minutes=GRACE_MINUTES):
                    self._live_set(fid, datetime.fromisoformat(due_at).date(), "callback", 1, "queued")
            for fid, due_at, source_date in due:
                if datetime.fromisoformat(due_at) < now - timedelta(minutes=GRACE_MINUTES):
                    self._cb_update(fid, due_at, status="missed",
                                    note=f"not placed within {GRACE_MINUTES} min of the requested time")
                    continue
                self._cb_update(fid, due_at, status="calling", note=now.isoformat(timespec="seconds"))   # claimed at
                try:
                    placed += self._callback_one(ports, fid, due_at, date.fromisoformat(source_date))
                except Exception as exc:                    # never retried, never stops the others
                    self._cb_update(fid, due_at, status="error", note=type(exc).__name__)
                finally:
                    self._live_clear(fid)
        return placed

    def _callback_one(self, ports: Ports, fid: str, due_at: str, source_day: date) -> int:
        due_day = datetime.fromisoformat(due_at).date()
        farmer = ports.farmers.get_context(fid)
        if farmer is None or not farmer.active or not farmer.consent or not farmer.phone or self._is_paused(fid):
            self._cb_update(fid, due_at, status="skipped", note="not callable (consent, active, phone or asked to stop)")
            return 0
        w = ports.weather.get_weather(farmer.place_name, farmer.latitude, farmer.longitude, due_day)
        if w is None:
            self._cb_update(fid, due_at, status="skipped", note="weather_unavailable")
            return 0
        self._live_set(fid, due_day, "callback", 1, "calling")
        try:
            res = self.dialler.place(farmer.phone, _LANG_NAMES[farmer.language], self._variables(farmer, w))
        except Exception as exc:
            res = ProviderCallResult(AttemptStatus.FAILED, error=type(exc).__name__)
        out: dict = {}
        if res.status is AttemptStatus.ANSWERED:
            try:
                out = self.dialler.outputs(res.provider_call_id)
            except Exception:
                out = {}
        self._finish_callback(ports, farmer, fid, due_at, source_day, due_day, res, out, w.source)
        return 1

    def _finish_callback(self, ports: Ports, farmer: FarmerContext, fid: str, due_at: str, source_day: date, due_day: date,
                         res: ProviderCallResult, out: dict, weather_source: str, at: datetime | None = None) -> None:
        """Keeps a callback's result, then handles a stop request or a farmer who asks to be called later again."""
        for n in (1, 2, 3):                                 # a free attempt number for that day
            try:
                ports.ledger.record_attempt(CallAttempt(
                    farmer_id=fid, call_date=due_day, attempt_no=n, status=res.status, language=farmer.language,
                    message_text="(callback)", provider_call_id=res.provider_call_id, duration_s=res.duration_s,
                    error=res.error, weather_source=weather_source))
                if due_day != source_day:                   # a new day: this call is that day's one call
                    ports.ledger.record_day_result(FarmerDayResult(fid, due_day, final_result(res.status), 1))
                break
            except IntegrityError:
                ports.ledger.db.rollback()
                continue
        self._cb_update(fid, due_at, status=res.status.value, note=res.error, attempt_id=res.provider_call_id,
                        call_summary=out.get("call_summary", ""), understood_weather=out.get("understood_weather", ""))
        if out.get("stop_calls_requested") == "yes":
            self._note_stop(fid, due_day)
        elif out.get("callback_time"):                      # asked to be called later again: allowed twice at most
            with self.lock:
                used = self.db.execute("SELECT reschedules FROM dash_callbacks WHERE farmer_id=? AND due_at=?",
                                       (fid, due_at)).fetchone()[0] or 0
            if used < MAX_RESCHEDULES:
                self._schedule_callback(fid, source_day, out["callback_time"], now=at, reschedules=used + 1)
            else:
                self._alert("callback_limit", fid,
                            f"Asked to move the callback again after {MAX_RESCHEDULES} reschedules; no more callbacks.")

    def callbacks(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT c.farmer_id, f.name, c.due_at, c.status, c.note, c.call_summary, "
                                   "c.understood_weather, c.requested_text FROM dash_callbacks c "
                                   "LEFT JOIN dash_farmers f ON f.farmer_id=c.farmer_id ORDER BY c.due_at DESC").fetchall()
        keys = ("farmer_id", "farmer_name", "due_at", "status", "note", "summary", "understood", "asked")
        return [dict(zip(keys, r)) for r in rows]

    # -- the background timer: callbacks when due, and the daily send when switched on ------------------------------
    def tick(self) -> bool:
        """One pass over what is due: callbacks, retries and the daily send. Only one pass runs at a time, whether it comes
        from the background loop or from POST /api/tick, so a wake-up call can never double a call. Returns False if
        another pass was already running."""
        if not self._tick_lock.acquire(blocking=False):
            return False
        try:
            self._tick_once()
            return True
        finally:
            self._tick_lock.release()

    # -- a call whose result was never saved (the process stopped while the farmer was on the phone) ------------------------
    def _claimed_at(self, note: str, due_at: str) -> datetime:
        try:
            return datetime.fromisoformat(note)
        except (TypeError, ValueError):
            return datetime.fromisoformat(due_at)           # claims made before the claim time was kept

    def _find_call(self, ports: Ports, fid: str, claimed: datetime):
        farmer = ports.farmers.get_context(fid)
        find = getattr(self.dialler, "find_call", None)
        if farmer is None or find is None:
            return None
        try:
            return find(farmer.phone, claimed - timedelta(minutes=2), claimed + timedelta(minutes=20))
        except Exception:
            return None

    def recover_interrupted(self, now: datetime | None = None) -> int:
        """A retry or callback that was taken (status calling) more than INTERRUPTED_MINUTES ago and never finished means the
        process stopped mid-call (a restart, a crash). Ask the provider what happened to that call: if it is there, save its
        result and handle it as if nothing had happened (a callback time the farmer asked for is scheduled, counted from
        when the call ended). If it is not there, drop the claim and tell the team; nobody is dialled twice on a guess.
        Returns how many calls were recovered."""
        now = now or self._now()
        with self.lock:
            retries = self.db.execute("SELECT farmer_id, call_date, attempt_no, due_at, note FROM dash_retries "
                                      "WHERE status='calling'").fetchall()
            callbacks = self.db.execute("SELECT farmer_id, due_at, source_date, note FROM dash_callbacks "
                                        "WHERE status='calling'").fetchall()
        limit = timedelta(minutes=INTERRUPTED_MINUTES)
        stale_r = [r for r in retries if self._claimed_at(r[4], r[3]) + limit < now]
        stale_c = [r for r in callbacks if self._claimed_at(r[3], r[1]) + limit < now]
        if not stale_r and not stale_c:
            return 0
        recovered = 0
        with self.cb_lock:
            ports = self._make_ports()
            for fid, day, attempt_no, due_at, note in stale_r:
                found = self._find_call(ports, fid, self._claimed_at(note, due_at))
                if found is None:
                    self._retry_update(fid, day, attempt_no, "dropped", "interrupted: no call found")
                    self._alert("interrupted_call", fid, "A retry call was interrupted and no call was found at the provider. "
                                                         "Use the Call button if the farmer still needs one.")
                    continue
                res, ended = found
                ended = ended.astimezone(self._now().tzinfo or IST)
                out = self._outputs(res)
                farmer = ports.farmers.get_context(fid)
                try:
                    ports.ledger.record_attempt(CallAttempt(
                        farmer_id=fid, call_date=date.fromisoformat(day), attempt_no=attempt_no, status=res.status,
                        language=farmer.language, message_text="(recovered)", provider_call_id=res.provider_call_id,
                        duration_s=res.duration_s, error=res.error, weather_source="recovered"))
                except IntegrityError:
                    ports.ledger.db.rollback()
                ports.ledger.db.execute("UPDATE day_results SET result=?, attempts=? WHERE farmer_id=? AND call_date=?",
                                        (final_result(res.status).value, attempt_no, fid, day))
                ports.ledger.db.commit()
                self._store_outcome(fid, date.fromisoformat(day), farmer, None, attempt_no, res, out, at=ended,
                                    weather=self._saved_weather(fid, day))
                self._retry_update(fid, day, attempt_no, "done", "recovered after an interruption")
                recovered += 1
            for fid, due_at, source_date, note in stale_c:
                found = self._find_call(ports, fid, self._claimed_at(note, due_at))
                if found is None:
                    self._cb_update(fid, due_at, status="error", note="interrupted: no call found")
                    self._alert("interrupted_call", fid, "A callback was interrupted and no call was found at the provider. "
                                                         "Use the Call button if the farmer still needs one.")
                    continue
                res, ended = found
                ended = ended.astimezone(self._now().tzinfo or IST)
                farmer = ports.farmers.get_context(fid)
                self._finish_callback(ports, farmer, fid, due_at, date.fromisoformat(source_date),
                                      datetime.fromisoformat(due_at).date(), res, self._outputs(res), "recovered", at=ended)
                recovered += 1
        return recovered

    def _outputs(self, res: ProviderCallResult) -> dict:
        if res.status is not AttemptStatus.ANSWERED:
            return {}
        try:
            return self.dialler.outputs(res.provider_call_id)
        except Exception:
            return {}

    def _saved_weather(self, fid: str, day: str) -> dict:
        with self.lock:
            row = self.db.execute("SELECT weather FROM dash_results WHERE farmer_id=? AND call_date=?", (fid, day)).fetchone()
        return json.loads(row[0]) if row and row[0] else {}

    def start_tick(self) -> bool:
        """For an outside timer (POST /api/tick): run one pass in the background and return at once. The timer's only
        job is to wake a sleeping host and nudge it; what is due is decided here, exactly as when the loop runs it."""
        if self._tick_lock.locked():
            return False
        threading.Thread(target=self.tick, daemon=True).start()
        return True

    def _tick_once(self) -> None:
        self.recover_interrupted()
        self.run_due_callbacks()
        self.run_due_retries()
        now = self._now()
        if (self.auto_dispatch_enabled() and now.time() >= DAILY_RUN_TIME
                and self._get_setting("last_auto_run_date") != now.date().isoformat() and not self.running):
            self._set_setting("last_auto_run_date", now.date().isoformat())
            self._set_setting("last_auto_run", now.isoformat(timespec="seconds"))
            if now.time() > CALL_TO:                       # backend was down all day: too late to call anyone
                self._alert("run_skipped", "",
                            f"Today's calls were skipped: the backend was not running until after {CALL_TO:%H:%M}.")
            else:
                self.start_fire(now.date())

    def scheduler_loop(self, every: int = 30) -> None:
        import time as _t
        while True:
            try:
                self.tick()
            except Exception:
                pass
            _t.sleep(every)

    # -- reading results for the dashboard -------------------------------------------------------------------------
    def _all_attempts(self) -> dict[tuple[str, str], list[dict]]:
        """Every attempt, grouped by (farmer, day), in one query (one round trip, however many calls are listed)."""
        with self.lock:
            try:
                rows = self.db.execute("SELECT farmer_id, call_date, attempt_no, status, duration_s, error FROM attempts "
                                       "ORDER BY farmer_id, call_date, attempt_no").fetchall()
            except OperationalError:
                rows = []
        label = {"answered": "Answered", "no_answer": "No Answer or Rejected", "busy": "Busy", "failed": "Failed"}
        out: dict[tuple[str, str], list[dict]] = {}
        for fid, day, n, status, dur, err in rows:
            out.setdefault((fid, day), []).append({"attempt_number": n, "status": label.get(status, status),
                                                   "duration_seconds": dur or 0, "error_message": err or ""})
        return out

    @staticmethod
    def _status_for(status: str, understood: str, has_callback: bool, retry_pending: bool = False,
                    callback_status: str | None = None) -> tuple[str, str]:
        """The dashboard's status and disposition for one stored result."""
        if retry_pending and not has_callback:
            return "Retrying", "Retry scheduled"
        if status == "answered":
            if has_callback:
                if callback_status in ("missed", "skipped"):          # the requested time passed and nobody was called
                    return "Callback Missed", "Callback not placed in time"
                if callback_status in ("answered", "no_answer", "busy", "failed", "error"):
                    return "Callback Done", {"answered": "Callback placed", "no_answer": "Callback not picked up",
                                             "busy": "Callback busy"}.get(callback_status, "Callback failed")
                return "Callback Scheduled", "Callback Requested"
            if understood == "declined":
                return "Declined", "Not needed today"
            if understood == "no_response":
                return "Unanswered", "No response (hello or silence)"
            if understood == "yes":
                return "Completed", "Weather Delivered"
            return "Not Confirmed", "Heard, not confirmed"
        if status in ("no_answer", "busy"):
            return "Unanswered", "No Answer or Rejected" if status == "no_answer" else "Busy"
        if status in ("failed", "error"):
            return "Failed", "Provider Error"
        return "Skipped", "Skipped"

    def calls(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT r.farmer_id, r.call_date, r.status, r.note, r.weather, r.attempt_id, r.mode, r.language, "
                "r.duration_s, r.call_summary, r.callback_time, r.understood_weather, r.stop_calls_requested, "
                "r.transcript, r.updated_at, f.name, f.phone, f.village, f.district "
                "FROM dash_results r LEFT JOIN dash_farmers f ON f.farmer_id=r.farmer_id "
                "ORDER BY r.updated_at DESC").fetchall()
            cbs = self.db.execute("SELECT farmer_id, source_date, due_at, status FROM dash_callbacks").fetchall()
            rts = self.db.execute("SELECT farmer_id, call_date, due_at FROM dash_retries "
                                  "WHERE status IN ('pending','calling')").fetchall()
        retry_due = {(fid, day): due for fid, day, due in rts}
        all_attempts = self._all_attempts()
        by_day: dict[tuple[str, str], tuple[str, str]] = {}
        for fid, src, due, st in cbs:
            by_day[(fid, src)] = (due, st)
        out = []
        for (fid, day, status, note, weather, attempt_id, mode, lang, dur, summary, cb_text, understood, stop,
             transcript, updated, name, phone, village, district) in rows:
            cb = by_day.get((fid, day))
            retry_at = retry_due.get((fid, day))
            dash_status, disposition = self._status_for(status, understood or "", cb is not None, retry_at is not None,
                                                        cb[1] if cb else None)
            attempts = all_attempts.get((fid, day), [])
            if status == "skipped":
                disposition = (note or "skipped").replace("_", " ").title()
            elif status == "failed" and note:
                disposition = f"Failed: {scrub(note)[:120]}"
            w = json.loads(weather) if weather else {}
            cb_due = datetime.fromisoformat(cb[0]) if cb else None
            out.append({
                "call_id": f"{fid}-{day}", "farmer_id": fid, "farmer_name": name or f"Farmer {fid}",
                "phone_number": mask_phone(phone or ""), "location": ", ".join(x for x in (village, district) if x),
                "village": village or "", "district": district or "", "call_date": day, "created_at": updated,
                "language": _LANG_LABELS[Language(lang)] if lang else "",
                "weather_temp": f"{w['temp_min']}-{w['temp_max']}" if w else None,
                "weather_windspeed": w.get("wind"), "weather_rainfall": w.get("rain"), "weather_humidity": w.get("humidity"),
                "weather_source": w.get("source", ""), "status": dash_status, "disposition": disposition,
                "note": scrub(note or ""), "retry_count": max(len(attempts) - 1, 0), "duration_seconds": dur or 0,
                "attempts_used": len(attempts) - min(sum(1 for x in attempts if x["error_message"] == NETWORK_DROP), MAX_FREE_RETRIES), "max_attempts": self.settings.max_attempts,
                "next_attempt_at": datetime.fromisoformat(retry_at).strftime("%d %b, %I:%M %p") if retry_at else None,
                "scheduled_callback_time": cb_due.strftime("%d %b, %I:%M %p") if cb_due else None,
                "callback_status": cb[1] if cb else None, "callback_requested_text": cb_text or "",
                "summary": summary or "", "understood_weather": understood or "", "stop_calls_requested": stop or "",
                "transcript": json.loads(transcript) if transcript else [], "attempts_log": attempts,
                "call_mode": mode or "", "attempt_id": attempt_id or ""})
        out += self._test_rows()
        live = {lv[0]: lv for lv in self._live_rows()}
        shown = set()
        for c in out:                                       # a farmer being called now: the row says so
            lv = live.get(c["farmer_id"])
            if lv and not c.get("is_test") and lv[2] != "test" and lv[1] == c["call_date"]:
                c["status"], c["disposition"] = self._live_label(lv)
                c.update(created_at=lv[5], next_attempt_at=None, live=True)
                shown.add(c["farmer_id"])
        out += [self._live_row(lv) for fid, lv in live.items() if fid not in shown]
        out.sort(key=lambda c: c["created_at"] or "", reverse=True)
        return out

    def call(self, call_id: str) -> dict | None:
        return next((c for c in self.calls() if c["call_id"] == call_id), None)

    def weather_for(self, lat: float, lon: float) -> dict | None:
        w = self._weather.get_weather("Location", lat, lon, self._now().date())
        if w is None:
            return None
        return {"source": w.source, "temperature": f"{w.temp_min_c}-{w.temp_max_c}", "temp_min": w.temp_min_c,
                "temp_max": w.temp_max_c, "wind_speed": w.wind_kmh, "rainfall_probability": w.rain_chance_pct,
                "relative_humidity": w.humidity_pct}
