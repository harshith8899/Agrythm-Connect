"""The dashboard's backend service: import farmers, send the day's calls, keep the results, run callbacks.

It reuses the engine's checks (consent, active, phone, real weather, once per farmer per day) and the weather store
(retries, then the saved 7-day forecast). Calls go through a dialler (Sarvam or the simulated mock). Results are kept
in the same SQLite file as the call ledger, in the shape the React dashboard reads (see calls()).

Farmer phone numbers are stored here (a call needs them) but are never returned unmasked and never logged.
Callbacks: when the agent records a time the farmer asked for (`callback_time`), one call is placed at that time, inside
the calling window (5:00 to 22:00 IST), at most 30 minutes late, and never retried.
"""
from __future__ import annotations

import hashlib
import json
import queue
import re
import sqlite3
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Callable

from .adapters.dialers import OUTPUT_VARS, make_dialler
from .adapters.local import SQLiteLedger
from .adapters.mailer import MailNotConfigured, make_mailer
from .adapters.translate import TranslateError, make_translator
from .adapters.mock import MockVoice, MockWeather
from .adapters.weatherapi import geocode, make_weather
from .adapters.sarvam_agent import _LANG_NAMES, to_e164
from .adapters.sarvam_campaign import IST, scrub
from .adapters.sheet import _ALIASES, _LANG, _key, _read_rows, load_farmers
from .adapters.weather_store import StoredWeather
from .config import Settings
from .db import IntegrityError, OperationalError, connect, table_columns
from .contracts import (AttemptStatus, CallAttempt, CallRequest, FarmerContext, FarmerDayResult, Language,
                        ProviderCallResult)
from .engine import Ports, final_result, prepare_call
from .messages import (KIND_CALLBACK_MISSED, KIND_CALLBACK_WEATHER, KIND_MISSED, KIND_WEATHER, build_email,
                       has_full_weather)
from .script import format_now, weather_variables

CALL_FROM, CALL_TO = dtime(5, 0), dtime(22, 0)   # callbacks only inside these hours (IST), set by the team on 5 Nov
GRACE_MINUTES = 30        # a callback not placed within this long after its time is marked missed, not called late
MAX_RELATIVE_MINUTES = 12 * 60
NETWORK_DROP = "network_drop"   # set by the Sarvam adapter when a connected call was cut by the network
LIVE_RECOVER_MINUTES = 6     # an In Queue or In Call row this old belongs to a process that stopped (a call is given up after 5 minutes)
LIVE_STALE_MINUTES = 20      # an In Queue or In Call row older than this belongs to a process that stopped: it is dropped
INTERRUPTED_MINUTES = 10     # a retry or callback still 'calling' after this long means the process stopped mid-call
MAX_FREE_RETRIES = 2        # a dropped call (network) is retried twice a day without counting as an attempt
NETWORK_RETRY_MIN = 5
MAX_RESCHEDULES = 2       # a farmer may move a callback at most twice (team, 5 Nov)
ALREADY_NOTE = "Send skipped: already called today (one call per farmer per day)"
DAILY_RUN_TIME = dtime(9, 0)
INBOUND_RETRY_S = 300                              # a failed push to the inbound line is tried again after this many seconds
RETRY_GAPS_MIN = (30, 60)        # client rule: 30 min before attempt 2, then 1 hour before attempt 3 (3 attempts)
FAILURE_RETRY_GAPS_MIN = (30,)   # a provider or number failure is retried once, then shown to the team

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dash_farmers(
  farmer_id TEXT PRIMARY KEY, name TEXT, phone TEXT, language TEXT, village TEXT, district TEXT, state TEXT,
  lat REAL, lon REAL, consent INT, active INT, email TEXT DEFAULT '');
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
-- every call made to the inbound line, whoever rang (the dashboard's incoming calls)
CREATE TABLE IF NOT EXISTS dash_incoming(
  attempt_id TEXT PRIMARY KEY, call_date TEXT, at TEXT, last4 TEXT, farmer_id TEXT, duration_s INT, outcome TEXT, note TEXT);
-- English text for what was said (a translation is made once and kept); h is a hash of the language and the text
CREATE TABLE IF NOT EXISTS dash_translations(h TEXT PRIMARY KEY, english TEXT);
-- a farmer we could not reach today, told to the inbound line so that, if they ring back, the agent knows who they are
CREATE TABLE IF NOT EXISTS dash_inbound(
  farmer_id TEXT, call_date TEXT, context TEXT, status TEXT, note TEXT, pushed_at TEXT,
  PRIMARY KEY(farmer_id, call_date));
-- one written message (email) per farmer, day and kind: the primary key keeps it from going out twice
CREATE TABLE IF NOT EXISTS dash_messages(
  farmer_id TEXT, call_date TEXT, kind TEXT, channel TEXT, status TEXT, note TEXT, at TEXT,
  PRIMARY KEY(farmer_id, call_date, kind));
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


_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def _clean_email(value, strict: bool = False) -> str:
    """A farmer's email address, or '' when there is none. A bad one is refused when typed in, ignored in a sheet."""
    v = str(value or "").strip().lower()
    if not v:
        return ""
    if _EMAIL.match(v):
        return v
    if strict:
        raise ValueError("email address is not valid")
    return ""


def mask_email(email: str) -> str:
    """Shown on the dashboard instead of the address: 'r***@gmail.com'."""
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _caller_keys(phone: str) -> list[str]:
    """How a caller can be recognised: the SHA-256 of the +91 number (what Sarvam's call record carries as the hashed contact,
    exact) and the last 4 digits (a fallback when the record has no hash)."""
    keys = [re.sub(r"\D", "", phone or "")[-4:]]
    try:
        keys.append(hashlib.sha256(to_e164(phone).encode()).hexdigest())
    except ValueError:
        pass
    return keys


def _error_detail(exc: BaseException) -> str:
    """What to record about an error: its type and a code, never its message (it could quote an address or a number)."""
    safe = getattr(exc, "safe_text", "")
    if safe:
        return str(safe)[:200]
    name = type(exc).__name__
    code = getattr(exc, "smtp_code", None)
    if isinstance(code, int):
        return f"{name} (SMTP {code})"
    errno = getattr(exc, "errno", None) if isinstance(exc, OSError) else None
    return f"{name} (errno {errno})" if isinstance(errno, int) else name


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
            r = self.db.execute("SELECT farmer_id,name,phone,language,village,district,lat,lon,consent,active,email "
                                "FROM dash_farmers WHERE farmer_id=?", (farmer_id,)).fetchone()
        if not r:
            return None
        return FarmerContext(r[0], r[1], Language(r[3]), r[4] or r[5], r[6], r[7], bool(r[8]), bool(r[9]), phone=r[2], email=r[10] or "")


class DashboardService:
    def __init__(self, db_path: str, weather=None, dialler=None, note: str = "", env: dict | None = None,
                 now: Callable[[], datetime] | None = None, mailer=None, translator=None):
        import os
        self.db_path = db_path
        self._now = now or (lambda: datetime.now(IST))
        self.db = connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript(_SCHEMA)
        if "reschedules" not in table_columns(self.db, "dash_callbacks"):      # databases made before the reschedule limit
            self.db.execute("ALTER TABLE dash_callbacks ADD COLUMN reschedules INT DEFAULT 0")
        if "hidden" not in table_columns(self.db, "dash_messages"):             # email log rows can be removed from the list
            self.db.execute("ALTER TABLE dash_messages ADD COLUMN hidden INT DEFAULT 0")
        if "email" not in table_columns(self.db, "dash_farmers"):               # databases made before email messages
            self.db.execute("ALTER TABLE dash_farmers ADD COLUMN email TEXT DEFAULT ''")
        self.settings = Settings.from_env()
        self.dialler, self.note = (dialler, note) if dialler else make_dialler(env)
        self.mailer = mailer or make_mailer(env)
        self.translator = translator if translator is not None else make_translator(env)
        # testing: every farmer's message goes to this one address (as if it were that farmer's), with the farmer named in the subject
        self.mail_test_to = _clean_email((env if env is not None else os.environ).get("GATE0_MAIL_TEST_TO", ""))
        e = env if env is not None else os.environ
        self.real_weather = e.get("GATE0_WEATHER", "open_meteo") != "mock"
        self._weather = weather or (make_weather(e) if self.real_weather else MockWeather())
        self.ports: Ports | None = None      # engine connections are made inside the working thread (SQLite is per thread)
        self.running = False
        self.last_run: dict | None = None
        self.cb_lock = threading.Lock()
        self._tick_lock = threading.Lock()
        self._manual: set[str] = set()          # farmers with a call placed by hand in progress
        self.async_inbound = True               # farmer changes update the inbound line in the background (tests switch it off)
        # Calls are placed at the same time, as many as there are farmers (up to this many): the long part of a call is waiting
        # for Sarvam, which costs no database. Database work borrows one of a few shared connections for a moment (the
        # Supabase pooler allows few connections), so a hundred calls never mean a hundred connections.
        self.max_parallel = max(1, int(e.get("GATE0_MAX_PARALLEL_CALLS") or 100))
        self.db_pool = max(1, int(e.get("GATE0_DB_POOL") or 4))
        self._ports_pool: queue.LifoQueue = queue.LifoQueue()
        self._ports_made = 0
        self._pool_lock = threading.Lock()
        self.draining = False                   # set when the host asks the process to stop: finish the calls, start no new one

    def _make_ports(self) -> Ports:
        return Ports(DBFarmers(self.db, self.lock), SQLiteLedger(self.db_path), StoredWeather(
            self._weather, self.db_path, retry_minutes=(), sleep=lambda s: None),   # one request per place and day: the weather retries are the service's own, later
            MockVoice(), None)

    @contextmanager
    def _ports_ctx(self, ports: Ports | None = None):
        """The engine connections for a moment of database work: the ones given, or one borrowed from the shared few (it
        waits when all are in use) and given back after. Never hold it while waiting for a call."""
        if ports is not None:
            yield ports
            return
        borrowed = None
        try:
            borrowed = self._ports_pool.get_nowait()
        except queue.Empty:
            with self._pool_lock:
                if self._ports_made < self.db_pool:
                    self._ports_made += 1
                    borrowed = self._make_ports()
            if borrowed is None:
                borrowed = self._ports_pool.get()
        try:
            yield borrowed
        finally:
            self._ports_pool.put(borrowed)

    def _run_parallel(self, jobs: list, work) -> list:
        """work(job) for every job at the same time (up to max_parallel at once); the results, in order. work never raises."""
        if not jobs:
            return []
        with ThreadPoolExecutor(max_workers=min(len(jobs), self.max_parallel), thread_name_prefix="call") as pool:
            return list(pool.map(work, jobs))

    def _warm_weather(self, items: list[tuple[str, date]]) -> None:
        """One weather request per place and day, made before the calls start together, so a hundred farmers in a few places
        do not all ask the weather service at once. Never raises."""
        seen: set = set()
        try:
            with self._ports_ctx(None) as p:
                for fid, day in items:
                    f = p.farmers.get_context(fid)
                    if f is None or (f.place_name, f.latitude, f.longitude, day) in seen:
                        continue
                    seen.add((f.place_name, f.latitude, f.longitude, day))
                    try:
                        p.weather.get_weather(f.place_name, f.latitude, f.longitude, day)
                    except Exception:
                        pass
        except Exception:
            pass

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
        """A note for the team. The same note for the same farmer is not repeated within 30 minutes (a failing push or
        mail would otherwise fill the list)."""
        since = (self._now() - timedelta(minutes=30)).isoformat(timespec="seconds")
        with self.lock:
            if self.db.execute("SELECT 1 FROM dash_alerts WHERE kind=? AND farmer_id=? AND text=? AND at>=?",
                               (kind, fid, text, since)).fetchone():
                return
            self.db.execute("INSERT INTO dash_alerts(at, kind, farmer_id, text) VALUES(?,?,?,?)",
                            (self._now().isoformat(timespec="seconds"), kind, fid, text))
            self.db.commit()

    def alerts(self, limit: int = 50) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT a.at, a.kind, a.farmer_id, f.name, a.text, a.id FROM dash_alerts a "
                                   "LEFT JOIN dash_farmers f ON f.farmer_id=a.farmer_id ORDER BY a.id DESC LIMIT ?",
                                   (limit,)).fetchall()
        return [{"id": r[5], "at": r[0], "kind": r[1], "farmer_id": r[2], "farmer_name": r[3] or "", "text": r[4]} for r in rows]

    def dismiss_alerts(self, ids: list | None = None) -> int:
        """Deletes the notes with these ids, or every note when ids is None. Returns how many were removed."""
        with self.lock:
            if ids is None:
                n = self.db.execute("SELECT COUNT(*) FROM dash_alerts").fetchone()[0]
                self.db.execute("DELETE FROM dash_alerts")
            else:
                clean = [int(i) for i in ids if str(i).lstrip("-").isdigit()]
                n = 0
                for i in clean:
                    n += self.db.execute("SELECT COUNT(*) FROM dash_alerts WHERE id=?", (i,)).fetchone()[0]
                    self.db.execute("DELETE FROM dash_alerts WHERE id=?", (i,))
            self.db.commit()
        return n

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
                extra[get("farmer_id")] = (get("village"), get("district"), get("state"), get("email"))
        with self.lock:
            for f in farmers:
                village, district, state, email = extra.get(f.farmer_id, ("", "", "", ""))
                self.db.execute("DELETE FROM dash_paused WHERE farmer_id=?", (f.farmer_id,))   # sheet updated by a person
                self.db.execute("INSERT OR REPLACE INTO dash_farmers(farmer_id,name,phone,language,village,district,state,"
                                "lat,lon,consent,active,email) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                    f.farmer_id, f.display_name, f.phone, f.language.value, village, district, state,
                    f.latitude, f.longitude, int(f.consent), int(f.active), _clean_email(email)))
            self.db.commit()
        self._refresh_inbound_later([f.farmer_id for f in farmers])
        return {"imported": len(farmers), "no_location": [f.farmer_id for f in farmers if not (f.latitude or f.longitude)]}

    _FARMER_COLS = "farmer_id,name,phone,language,village,district,state,lat,lon,consent,active,email"

    @staticmethod
    def _farmer_dict(r) -> dict:
        return {"farmer_id": r[0], "farmer_name": r[1], "phone_number": mask_phone(r[2]),
                "preferred_language": _LANG_LABELS[Language(r[3])], "village": r[4], "district": r[5], "state": r[6],
                "located": bool(r[7] or r[8]), "call_consent": "Yes" if r[9] else "No", "active": "Yes" if r[10] else "No",
                "email": mask_email(r[11] or "")}

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
        email = _clean_email(data.get("email"), strict=True)
        fid = str(data.get("farmer_id") or "").strip() or self._next_farmer_id()
        with self.lock:
            if self.db.execute("SELECT 1 FROM dash_farmers WHERE farmer_id=?", (fid,)).fetchone():
                raise ValueError(f"Farmer ID {fid} already exists")
        lat, lon = self._locate(village, district, state)
        consent = self._yes_no(data.get("call_consent", False), "call consent")
        active = self._yes_no(data.get("active", True), "active")
        with self.lock:
            self.db.execute("INSERT INTO dash_farmers(farmer_id,name,phone,language,village,district,state,lat,lon,"
                            "consent,active,email) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                fid, name[:80], phone, lang.value, village, district, state, lat, lon, int(consent), int(active), email))
            self.db.commit()
        self._refresh_inbound_later([fid])
        return next(f for f in self.farmers() if f["farmer_id"] == fid)

    def update_farmer(self, fid: str, data: dict) -> dict:
        """Changes only the fields sent (name, phone, language, place, consent, active). A blank phone keeps the old one."""
        with self.lock:
            r = self.db.execute(f"SELECT {self._FARMER_COLS} FROM dash_farmers WHERE farmer_id=?", (fid,)).fetchone()
        if not r:
            raise KeyError(fid)
        _, name, phone, language, village, district, state, lat, lon, consent, active, email = r
        email = email or ""
        if "farmer_name" in data:
            name = str(data["farmer_name"]).strip()
            if not name:
                raise ValueError("farmer name is required")
        if str(data.get("phone_number") or "").strip():
            phone = self._clean_phone(data["phone_number"])
        if str(data.get("email") or "").strip():          # a blank email keeps the saved one, like the phone
            email = _clean_email(data["email"], strict=True)
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
                            "lon=?, consent=?, active=?, email=? WHERE farmer_id=?",
                            (name[:80], phone, language, village, district, state, lat, lon, consent, active, email, fid))
            self.db.commit()
        self._refresh_inbound_later([fid])
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

    def _live_reading(self, fid: str) -> None:
        """The call has ended: the row stays In Call but says the agent's notes are being read. Only an existing row changes."""
        try:
            with self.lock:
                self.db.execute("UPDATE dash_live SET state='reading' WHERE farmer_id=?", (fid,))
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
        if state == "reading":
            return "In Call", f"Call ended, reading what the agent recorded ({what})"
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

    def fire_one(self, fid: str, day: date, kind: str = "daily", ports: Ports | None = None) -> str:
        with self._ports_ctx(ports) as p:
            prepared = prepare_call(CallRequest(fid, day), p, self.settings)
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
        with self._ports_ctx(ports) as p:
            p.ledger.record_attempt(CallAttempt(
                farmer_id=fid, call_date=day, attempt_no=1, status=res.status, language=farmer.language,
                message_text=prepared.message, provider_call_id=res.provider_call_id, duration_s=res.duration_s,
                error=res.error, weather_source=w.source))
            p.ledger.record_day_result(FarmerDayResult(fid, day, final_result(res.status), 1))
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
            self._live_reading(farmer.farmer_id)                 # the log says the call ended while the agent's notes are read
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
        turns = out.get("transcript") or []
        if (res.status is AttemptStatus.ANSWERED and not out.get("understood_weather") and turns
                and any(m.get("speaker") == "Agent" for m in turns)
                and not any(m.get("speaker") == "Farmer" and (m.get("text") or "").strip() for m in turns)):
            out["understood_weather"] = "no_response"           # the farmer never spoke and the agent ended the call itself
            if not out.get("call_summary"):
                out["call_summary"] = "The farmer stayed silent and did not say anything."
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
        planned = self._plan_retry(fid, day, attempt_no, res.status, out, res.error, at)
        if not planned and res.status is AttemptStatus.FAILED:
            self._alert("provider_failure", fid,
                        f"The call failed and will not be retried ({scrub(res.error or 'provider error')[:80]}).")
        self._message_after_call(fid, day, res, out, weather, more_to_come=planned or self._has_callback(fid, day))
        self._refresh_inbound([fid])                        # what the inbound line should say if they ring us now

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
            for fid, day, attempt_no, due_at in due:
                if datetime.fromisoformat(due_at) >= now - timedelta(minutes=GRACE_MINUTES):
                    self._live_set(fid, date.fromisoformat(day), "retry", attempt_no, "queued")
            jobs = []
            for fid, day, attempt_no, due_at in due:
                if datetime.fromisoformat(due_at) < now - timedelta(minutes=GRACE_MINUTES):
                    self._retry_update(fid, day, attempt_no, "missed", f"not placed within {GRACE_MINUTES} min")
                    continue
                self._retry_update(fid, day, attempt_no, "calling", now.isoformat(timespec="seconds"))   # claimed at
                jobs.append((fid, day, attempt_no))
            self._warm_weather([(fid, date.fromisoformat(day)) for fid, day, _ in jobs])

            def work(job) -> int:                           # every due retry is placed at the same time
                fid, day, attempt_no = job
                try:
                    outcome = self._retry_one(None, fid, date.fromisoformat(day), attempt_no)
                except Exception as exc:
                    outcome = f"error: {type(exc).__name__}"
                finally:
                    self._live_clear(fid)
                self._retry_update(fid, day, attempt_no, "done" if outcome == "placed" else "dropped", "" if outcome == "placed" else outcome)
                return int(outcome == "placed")

            placed = sum(self._run_parallel(jobs, work))
        return placed

    def _retry_one(self, ports: Ports | None, fid: str, day: date, attempt_no: int) -> str:
        with self._ports_ctx(ports) as p:
            farmer = p.farmers.get_context(fid)
            if farmer is None or not farmer.active or not farmer.consent or not farmer.phone or self._is_paused(fid):
                return "not callable (consent, active, phone or asked to stop)"
            w = p.weather.get_weather(farmer.place_name, farmer.latitude, farmer.longitude, day)
        if w is None:
            return "weather_unavailable"
        self._live_set(fid, day, "retry", attempt_no, "calling")
        res, out = self._place(farmer, w)
        with self._ports_ctx(ports) as p:
            try:
                p.ledger.record_attempt(CallAttempt(
                    farmer_id=fid, call_date=day, attempt_no=attempt_no, status=res.status, language=farmer.language,
                    message_text="(retry)", provider_call_id=res.provider_call_id, duration_s=res.duration_s,
                    error=res.error, weather_source=w.source))
            except IntegrityError:
                p.ledger.db.rollback()          # a failed insert must not keep the database locked
            p.ledger.db.execute("UPDATE day_results SET result=?, attempts=? WHERE farmer_id=? AND call_date=?",
                                (final_result(res.status).value, attempt_no, fid, day.isoformat()))
            p.ledger.db.commit()
        self._store_outcome(fid, day, farmer, w, attempt_no, res, out)
        return "placed"

    def fire(self, day: date) -> None:
        self.running = True
        try:
            counts: dict[str, int] = {}
            with self._ports_ctx(None) as p:
                ids = p.farmers.list_callable_ids(day)
            for fid in ids:                                 # everyone waiting shows as In Queue from the start
                self._live_set(fid, day, "daily", 1, "queued")
            self._warm_weather([(fid, day) for fid in ids])

            def work(fid: str) -> str | None:               # every farmer is called at the same time
                if self.draining:                           # stopping: the rest stay In Queue and are reported after the restart
                    return None
                try:
                    return self.fire_one(fid, day)
                except Exception as exc:                    # one farmer never stops the others
                    self._save(fid, day, status="error", note=type(exc).__name__, mode=self.dialler.mode)
                    return "error"
                finally:
                    self._live_clear(fid)                   # a farmer who was not started never reaches here (they stay In Queue)

            for outcome in self._run_parallel(ids, work):
                if outcome is not None:
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
        is inactive, has no consent or asked to stop. It can be placed at any hour.

        mode "test" ignores the retry rules: the call is kept as its own Test row and never changes the farmer's real
        result, attempt count, retries, callbacks or alerts, and it can be repeated. Consent, active, phone, a stop
        request still apply; the calling hours do not."""
        if mode not in ("retry", "test"):
            raise ValueError('mode must be "retry" or "test"')
        if self.draining:
            raise ValueError("the server is restarting: try again in a minute")
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
        # no calling-hours check here: a call placed by hand can be made at any time (team, 15 Nov). The 05:00 to 22:00
        # window applies only to what the system places on its own (the daily send, retries and callbacks).
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
                        self.fire_one(fid, day, "manual", ports=ports)
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
            asked = out.get("callback_time") if out.get("stop_calls_requested") != "yes" else ""
            self._save_test(fid, stamp, res.status.value, res.error, weather, res.provider_call_id, farmer.language.value,
                            res.duration_s or 0, out)
            self._email_after_test(fid, res, out, weather)
            if asked:                                       # a test call books the callback the farmer asked for, like a real one
                self._schedule_callback(fid, self._now().date(), asked)
        finally:
            self._live_clear(fid)                           # the saved Test row replaces the In Call row

    def _email_after_test(self, fid: str, res: ProviderCallResult, out: dict, weather: dict) -> None:
        """A test call emails the test address (GATE0_MAIL_TEST_TO) as a real call would, so the email can be tried without
        a real farmer's day: recorded under its own key, so every test call sends and none uses up the real message. With no
        test address set a test call sends nothing, and never writes to a farmer's own address. Never raises."""
        try:
            if not self.mail_test_to or out.get("callback_time"):
                return
            if res.status is AttemptStatus.ANSWERED and out.get("understood_weather") == "yes":
                kind = KIND_WEATHER
            elif self._not_reached(res, out):
                kind = KIND_MISSED
            else:
                return
            self._send_message(fid, self._now().date(), kind, weather, record_kind=f"test:{kind}:{uuid.uuid4().hex[:8]}")
        except Exception:
            pass

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
            booked_cbs = {(f, s): d for f, s, d in self.db.execute(
                "SELECT farmer_id, source_date, due_at FROM dash_callbacks WHERE status<>'skipped'").fetchall()}
        label ={"answered": "Answered", "no_answer": "No Answer or Rejected", "busy": "Busy", "failed": "Failed"}
        out = []
        for (tid, fid, at, status, note, weather, attempt_id, lang, dur, summary, cb, understood, stop, transcript,
             name, phone, village, district) in rows:
            dash_status, disposition = self._status_for(status, understood or "", False, False, None, bool((cb or "").strip()))
            if dash_status == "Callback Requested":
                booked = booked_cbs.get((fid, at[:10]))
                disposition = (f"Callback requested for {cb} (booked for {datetime.fromisoformat(booked).strftime('%d %b, %I:%M %p')})"
                               if booked else f"Callback requested for {cb} (not booked: time not understood or outside hours)")
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
            for fid, due_at, source_date in due:
                if datetime.fromisoformat(due_at) >= now - timedelta(minutes=GRACE_MINUTES):
                    self._live_set(fid, datetime.fromisoformat(due_at).date(), "callback", 1, "queued")
            jobs = []
            for fid, due_at, source_date in due:
                if datetime.fromisoformat(due_at) < now - timedelta(minutes=GRACE_MINUTES):
                    self._cb_update(fid, due_at, status="missed",
                                    note=f"not placed within {GRACE_MINUTES} min of the requested time")
                    self._refresh_inbound([fid])
                    self._send_message(fid, datetime.fromisoformat(due_at).date(), KIND_CALLBACK_MISSED,
                                       self._saved_weather(fid, source_date),
                                       callback_time=datetime.fromisoformat(due_at).strftime("%H:%M"))
                    continue
                self._cb_update(fid, due_at, status="calling", note=now.isoformat(timespec="seconds"))   # claimed at
                jobs.append((fid, due_at, source_date))
            self._warm_weather([(fid, datetime.fromisoformat(due_at).date()) for fid, due_at, _ in jobs])

            def work(job) -> int:                           # every due callback is placed at the same time
                fid, due_at, source_date = job
                try:
                    return self._callback_one(None, fid, due_at, date.fromisoformat(source_date))
                except Exception as exc:                    # never retried, never stops the others
                    self._cb_update(fid, due_at, status="error", note=type(exc).__name__)
                    return 0
                finally:
                    self._live_clear(fid)

            placed = sum(self._run_parallel(jobs, work))
        return placed

    def _callback_one(self, ports: Ports | None, fid: str, due_at: str, source_day: date) -> int:
        due_day = datetime.fromisoformat(due_at).date()
        with self._ports_ctx(ports) as p:
            farmer = p.farmers.get_context(fid)
            if farmer is None or not farmer.active or not farmer.consent or not farmer.phone or self._is_paused(fid):
                self._cb_update(fid, due_at, status="skipped", note="not callable (consent, active, phone or asked to stop)")
                return 0
            w = p.weather.get_weather(farmer.place_name, farmer.latitude, farmer.longitude, due_day)
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
            self._live_reading(fid)
            try:
                out = self.dialler.outputs(res.provider_call_id)
            except Exception:
                out = {}
        with self._ports_ctx(ports) as p:
            self._finish_callback(p, farmer, fid, due_at, source_day, due_day, res, out, w.source,
                                  weather={"temp_min": w.temp_min_c, "temp_max": w.temp_max_c, "wind": w.wind_kmh,
                                           "rain": w.rain_chance_pct, "humidity": w.humidity_pct, "source": w.source})
        return 1

    def _finish_callback(self, ports: Ports, farmer: FarmerContext, fid: str, due_at: str, source_day: date, due_day: date,
                         res: ProviderCallResult, out: dict, weather_source: str, at: datetime | None = None,
                         weather: dict | None = None) -> None:
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
        self._refresh_inbound([fid], ports=ports)
        # a callback is never retried: the message follows it (the weather if understood, 'we tried to reach you' if not)
        self._message_after_call(fid, due_day, res, out, weather or self._saved_weather(fid, source_day.isoformat()),
                                 more_to_come=bool(out.get("callback_time")) and out.get("stop_calls_requested") != "yes",
                                 callback_time=datetime.fromisoformat(due_at).strftime("%H:%M"))

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

    # -- farmers who ring the number: only registered farmers are known to the inbound line --------------------------------
    @staticmethod
    def _not_reached(res: ProviderCallResult, out: dict) -> bool:
        """True when the call ended without the farmer being served and nothing else (a callback, a stop, a decline)
        explains it: not picked up, busy, cut off, or heard but not understood."""
        understood = out.get("understood_weather", "")
        if out.get("stop_calls_requested") == "yes" or understood in ("declined", "yes"):
            return False
        return (res.status in (AttemptStatus.NO_ANSWER, AttemptStatus.BUSY)
                or (res.status is AttemptStatus.ANSWERED and understood in ("no", "unclear", "no_response"))
                or (res.status is AttemptStatus.FAILED and res.error == NETWORK_DROP))

    def _inbound_ready(self) -> bool:
        return bool(getattr(self.dialler, "inbound_ready", False))

    def _caller_state(self, fid: str, day: date) -> tuple[str, str]:
        """What the inbound line should know about a farmer who rings today: (state, a sentence for the agent).
        unregistered (no consent or inactive: treated as an unknown number), stopped, callback HH:MM (waiting for the
        call they asked for), completed, declined, callback_missed HH:MM, missed (called today, not completed), not_called."""
        d = day.isoformat()
        with self.lock:
            f = self.db.execute("SELECT consent, active FROM dash_farmers WHERE farmer_id=?", (fid,)).fetchone()
            res = self.db.execute("SELECT understood_weather, stop_calls_requested FROM dash_results WHERE farmer_id=? "
                                  "AND call_date=?", (fid, d)).fetchone()
            cbs = self.db.execute("SELECT due_at, status, understood_weather FROM dash_callbacks WHERE farmer_id=? "
                                  "AND (source_date=? OR substr(due_at,1,10)=?) ORDER BY due_at", (fid, d, d)).fetchall()
            retry = self.db.execute("SELECT 1 FROM dash_retries WHERE farmer_id=? AND call_date=? AND status='pending'",
                                    (fid, d)).fetchone()
        if not f or not f[0] or not f[1]:
            return "unregistered", ""
        if self._is_paused(fid) or (res and res[1] == "yes"):
            return "stopped", "The farmer asked us to stop the calls."
        understood = (res[0] or "") if res else ""
        hhmm = lambda due: datetime.fromisoformat(due).strftime("%H:%M")      # noqa: E731
        pending = [c for c in cbs if c[1] == "pending"]
        if understood == "yes" or any((c[2] or "") == "yes" for c in cbs):
            return "completed", ("We already gave this farmer today's weather and they said they understood it, so there is no new "
                                 "update until tomorrow: do not give the weather again, even if they ask.")
        if pending:
            t = hhmm(pending[0][0])
            return f"callback {t}", (f"The farmer asked us to call back at {t} (24-hour time) and is calling before that; "
                                     "we will still call at that time.")
        if understood == "declined":
            return "declined", "The farmer told us they do not need today's weather."
        gone = [c for c in cbs if c[1] in ("missed", "no_answer", "busy", "failed")]
        if gone:
            t = hhmm(gone[-1][0])
            return f"callback_missed {t}", (f"The farmer had asked us to call back at {t} (24-hour time). We called at that "
                                            "time and could not reach them, and we will not call again today.")
        if res or retry:
            return "missed", "We called this farmer today to give the weather and could not reach them."
        return "not_called", "We have not called this farmer yet today; they are calling us first."

    def _refresh_inbound(self, fids: list[str] | None = None, force: bool = False, ports: Ports | None = None) -> int:
        """Tells the inbound line which numbers may ring and what happened today for each: every registered farmer (consent
        and active) with their name, place, weather and a sentence about today; a farmer who is no longer registered is sent
        with a blank name, so the agent treats the number as unknown. Only farmers whose state changed are sent, unless
        force (the daily full list). Returns how many were sent. Never raises."""
        try:
            if not self._inbound_ready():
                return 0
            day = self._now().date()
            with self.lock:
                ids = fids if fids is not None else [r[0] for r in self.db.execute("SELECT farmer_id FROM dash_farmers ORDER BY farmer_id")]
            entries: list[dict] = []
            for fid in ids:
                state, text = self._caller_state(fid, day)
                with self.lock:
                    prev = self.db.execute("SELECT context, status FROM dash_inbound WHERE farmer_id=? AND call_date=?",
                                           (fid, day.isoformat())).fetchone()
                    r = self.db.execute("SELECT name,phone,language,village,district,lat,lon FROM dash_farmers WHERE farmer_id=?",
                                        (fid,)).fetchone()
                if not r or not r[1] or (prev and prev[0] == state and prev[1] != "failed" and not force):
                    continue
                blank = {"farmer_name": "", "place_name": "", "temp_min_c": "", "temp_max_c": "", "wind_kmh": "",
                         "rain_chance_pct": "", "humidity_pct": "", "callback_context": ""}
                variables = dict(blank)
                if state not in ("unregistered", "stopped"):
                    weather = self._saved_weather(fid, day.isoformat())
                    if not has_full_weather(weather):
                        try:
                            if ports is None:
                                with self._ports_ctx(None) as p:
                                    w = p.weather.get_weather(r[3] or r[4], r[5], r[6], day)
                            else:
                                w = ports.weather.get_weather(r[3] or r[4], r[5], r[6], day)
                        except Exception:
                            w = None
                        weather = ({"temp_min": w.temp_min_c, "temp_max": w.temp_max_c, "wind": w.wind_kmh,
                                    "rain": w.rain_chance_pct, "humidity": w.humidity_pct} if w is not None else {})
                    variables.update({"farmer_name": r[0], "place_name": r[3] or r[4],
                                      "temp_min_c": str(weather.get("temp_min", "")), "temp_max_c": str(weather.get("temp_max", "")),
                                      "wind_kmh": str(weather.get("wind", "")), "rain_chance_pct": str(weather.get("rain", "")),
                                      "humidity_pct": str(weather.get("humidity", "")), "callback_context": text + " They are now calling us."})
                elif state == "stopped":
                    variables.update({"farmer_name": r[0], "callback_context": text + " They are now calling us."})
                entries.append({"fid": fid, "state": state, "phone": r[1], "language_name": _LANG_NAMES[Language(r[2])],
                                "variables": variables})
            if not entries:
                return 0
            status, note = "waiting", ""
            try:
                self.dialler.push_inbound_many(entries, f"roster-{self._now():%Y%m%d-%H%M%S}")
            except Exception as exc:                        # type only: an error text could quote a number
                status, note = "failed", _error_detail(exc)
                self._alert("inbound_push_failed", "", f"The call-back line could not be updated ({note}).")
            now = self._now().isoformat(timespec="seconds")
            with self.lock:
                for e in entries:
                    self.db.execute("INSERT OR REPLACE INTO dash_inbound VALUES(?,?,?,?,?,?)",
                                    (e["fid"], day.isoformat(), e["state"], status, note, now))
                self.db.commit()
            return len(entries)
        except Exception:
            return 0

    def _refresh_inbound_later(self, fids: list[str] | None = None) -> None:
        """The same, off the request that changed a farmer (it may need weather lookups)."""
        if not self._inbound_ready():
            return
        if self.async_inbound:
            threading.Thread(target=self._refresh_inbound, args=(fids,), daemon=True).start()
        else:
            self._refresh_inbound(fids)

    def _daily_inbound_roster(self) -> None:
        """Once a day, the full list again (the day's states start fresh)."""
        now = self._now()
        today = now.date().isoformat()
        if not self._inbound_ready():
            return
        last = self._get_setting("inbound_roster_try")
        if last:
            try:
                if (now - datetime.fromisoformat(last)).total_seconds() < INBOUND_RETRY_S:
                    return                                  # tried a moment ago: no hammering Sarvam while it refuses
            except ValueError:
                pass
        with self.lock:
            failed = self.db.execute("SELECT 1 FROM dash_inbound WHERE call_date=? AND status='failed' LIMIT 1", (today,)).fetchone()
        if self._get_setting("inbound_roster_date") != today or failed:
            self._set_setting("inbound_roster_try", now.isoformat(timespec="seconds"))
            self._refresh_inbound(force=True)               # a failed push is tried again, not left for tomorrow
            with self.lock:
                failed = self.db.execute("SELECT 1 FROM dash_inbound WHERE call_date=? AND status='failed' LIMIT 1", (today,)).fetchone()
            if not failed:
                self._set_setting("inbound_roster_date", today)

    def sync_inbound(self, now: datetime | None = None) -> int:
        """Brings in the calls made to the inbound line. Each is logged (dash_incoming) so the dashboard shows every incoming
        call, whoever rang; a call from a farmer we told the line about becomes that farmer's result (the weather email
        follows) and, when they were served (understood the weather, declined, asked to stop or for another time), their
        waiting retries are dropped, and a pending callback too if they understood, so nobody is rung right after calling
        us. One look at Sarvam's call records per pass, matched to farmers by the last 4 digits of the number (a number two
        farmers share is left alone). Run at the start of every pass, before any retry or callback is placed. Returns how
        many calls were brought in as results."""
        now = now or self._now()
        if not self._inbound_ready():
            return 0
        brought, seen, error = 0, 0, ""
        try:
            day = now.date()
            with self.lock:
                self.db.execute("UPDATE dash_inbound SET status='expired' WHERE status='waiting' AND call_date<?", (day.isoformat(),))
                self.db.commit()
                rows = self.db.execute("SELECT farmer_id, context FROM dash_inbound WHERE status='waiting' AND call_date=? "
                                       "AND context NOT IN ('unregistered','stopped')", (day.isoformat(),)).fetchall()
                known = {r[0] for r in self.db.execute("SELECT provider_call_id FROM attempts WHERE call_date=?",
                                                       (day.isoformat(),)).fetchall()}
                known |= {r[0] for r in self.db.execute("SELECT attempt_id FROM dash_incoming WHERE call_date=?",
                                                        (day.isoformat(),)).fetchall()}
                everyone = self.db.execute("SELECT farmer_id, phone, consent, active FROM dash_farmers").fetchall()
            ports = self._make_ports()
            waiting_by_key: dict[str, list[tuple[str, str]]] = {}
            for fid, context in rows:
                farmer = ports.farmers.get_context(fid)
                if farmer is not None and farmer.phone:
                    for k in _caller_keys(farmer.phone):
                        waiting_by_key.setdefault(k, []).append((fid, context))
            all_by_key: dict[str, list[tuple[str, bool]]] = {}
            for fid, phone, consent, active in everyone:
                if phone:
                    for k in _caller_keys(phone):
                        all_by_key.setdefault(k, []).append((fid, bool(consent and active)))
            start = datetime.combine(day, dtime(0, 0), IST)
            for call in self.dialler.find_inbound_calls(start, now, known):
                last4, res, ended = call[0], call[1], call[2]
                chash = call[3] if len(call) > 3 else ""
                key = chash or last4                          # the exact hash of the number when Sarvam gives it, else the last 4 digits
                seen += 1
                who = waiting_by_key.get(key, [])
                if len(who) == 1:
                    try:
                        if self._apply_inbound_call(ports, who[0][0], who[0][1], day, res, ended):
                            brought += 1
                        self._log_incoming(res, day, ended, last4, who[0][0], "answered", "Answered by the agent")
                    except Exception:                       # one farmer's problem never blocks the others
                        continue
                else:
                    known_fids = all_by_key.get(key, [])
                    if len(known_fids) == 1:
                        fid, registered = known_fids[0]
                        outcome, note = (("not_registered", "This farmer is inactive or has not given consent: the agent ends the call")
                                         if not registered else ("answered", "Answered by the agent (the line had no details for this farmer)"))
                    elif len(known_fids) > 1:
                        fid, outcome, note = "", "shared_number", "A number two farmers share: not matched to either"
                    else:
                        fid, outcome, note = "", "unknown_number", "Not a registered farmer: the agent ends the call"
                    self._log_incoming(res, day, ended, last4, fid, outcome, note)
                known.add(res.provider_call_id)
        except Exception as exc:                            # the dashboard shows this, so a failing look is not silent
            error = _error_detail(exc)
        try:
            self._set_setting("inbound_sync", json.dumps({"at": now.isoformat(timespec="seconds"), "seen": seen,
                                                          "applied": brought, "error": error}))
        except Exception:
            pass
        return brought

    def _log_incoming(self, res: ProviderCallResult, day: date, ended: datetime, last4: str, fid: str, outcome: str, note: str) -> None:
        """One row per call to the inbound line (the dashboard's incoming calls); never raises."""
        try:
            with self.lock:
                self.db.execute("INSERT OR IGNORE INTO dash_incoming VALUES(?,?,?,?,?,?,?,?)",
                                (res.provider_call_id, day.isoformat(), ended.astimezone(IST).isoformat(timespec="seconds"), last4,
                                 fid, res.duration_s or 0, outcome, note))
                self.db.commit()
        except Exception:
            pass

    def _incoming_rows(self) -> list[dict]:
        """Calls to the inbound line that are not a farmer's result (an unknown number, an inactive farmer, a shared number),
        shaped like the other call rows so the call log can list them with the incoming mark."""
        with self.lock:
            rows = self.db.execute("SELECT i.attempt_id, i.call_date, i.at, i.last4, i.farmer_id, i.duration_s, i.outcome, i.note, "
                                   "f.name, f.village, f.district FROM dash_incoming i LEFT JOIN dash_farmers f "
                                   "ON f.farmer_id=i.farmer_id WHERE i.outcome<>'answered' ORDER BY i.at DESC LIMIT 200").fetchall()
        out = []
        for attempt_id, call_date, at, last4, fid, dur, outcome, note, name, village, district in rows:
            title = {"not_registered": "Incoming call: not a registered farmer (inactive or no consent)",
                     "shared_number": "Incoming call: number shared by two farmers",
                     "unknown_number": "Incoming call: unknown number"}.get(outcome, "Incoming call")
            out.append({
                "call_id": f"IN-{attempt_id}", "direction": "incoming", "farmer_id": fid or "", "farmer_name": name or "Unknown number",
                "phone_number": "******" + last4, "location": ", ".join(x for x in (village, district) if x), "village": village or "",
                "district": district or "", "call_date": call_date, "created_at": at, "language": "", "weather_temp": None,
                "weather_windspeed": None, "weather_rainfall": None, "weather_humidity": None, "weather_source": "",
                "status": "Skipped", "disposition": title, "note": note, "retry_count": 0, "duration_seconds": dur or 0,
                "attempts_used": 0, "max_attempts": self.settings.max_attempts, "next_attempt_at": None,
                "scheduled_callback_time": None, "callback_status": None, "callback_requested_text": "", "summary": note,
                "understood_weather": "", "stop_calls_requested": "", "transcript": [], "attempts_log": [],
                "call_mode": self.dialler.mode, "attempt_id": attempt_id, "messages_sent": 0})
        return out

    def _apply_inbound_call(self, ports: Ports, fid: str, context: str, day: date, res: ProviderCallResult,
                            ended: datetime) -> int:
        farmer = ports.farmers.get_context(fid)
        if farmer is None:
            return 0
        out = self._outputs(res)
        weather = self._saved_weather(fid, day.isoformat())
        if not has_full_weather(weather):                   # rang before today's own call: the weather is not saved yet, and the email needs it
            try:
                w = ports.weather.get_weather(farmer.place_name, farmer.latitude, farmer.longitude, day)
            except Exception:
                w = None
            if w is not None:
                weather = {"temp_min": w.temp_min_c, "temp_max": w.temp_max_c, "wind": w.wind_kmh, "rain": w.rain_chance_pct,
                           "humidity": w.humidity_pct, "source": w.source}
        for n in range(1, 10):                              # a free attempt number for that day
            try:
                ports.ledger.record_attempt(CallAttempt(
                    farmer_id=fid, call_date=day, attempt_no=n, status=res.status, language=farmer.language,
                    message_text="(farmer called)", provider_call_id=res.provider_call_id, duration_s=res.duration_s,
                    error=res.error, weather_source=weather.get("source", "")))
                break
            except IntegrityError:
                ports.ledger.db.rollback()
        else:
            return 0
        if context == "completed":                          # asked for the weather again: the day's result stays as it is
            return 1
        cur = ports.ledger.db.execute("UPDATE day_results SET result=? WHERE farmer_id=? AND call_date=?",
                                      (final_result(res.status).value, fid, day.isoformat()))
        if cur.rowcount == 0:                               # rang before today's own call: this is the day's call
            ports.ledger.record_day_result(FarmerDayResult(fid, day, final_result(res.status), n))
        ports.ledger.db.commit()
        understood = out.get("understood_weather", "")
        self._store_outcome(fid, day, farmer, None, n, res, out, at=ended, weather=weather)
        served = understood in ("yes", "declined") or out.get("stop_calls_requested") == "yes" or bool(out.get("callback_time"))
        if served:                                          # nobody is rung again right after calling us
            with self.lock:
                self.db.execute("UPDATE dash_retries SET status='dropped', note='farmer called back' WHERE farmer_id=? "
                                "AND call_date=? AND status='pending'", (fid, day.isoformat()))
                if understood == "yes":
                    self.db.execute("UPDATE dash_callbacks SET status='skipped', note='farmer called back first' "
                                    "WHERE farmer_id=? AND status='pending'", (fid,))
                self.db.commit()
        self._refresh_inbound([fid])                        # what they should hear if they ring again today
        return 1

    def incoming(self, limit: int = 30) -> dict:
        """The incoming line at a glance: when it was last looked at, what the look found or the error, and the latest calls to it."""
        try:
            sync = json.loads(self._get_setting("inbound_sync") or "{}")
        except ValueError:
            sync = {}
        with self.lock:
            rows = self.db.execute("SELECT i.at, i.last4, i.farmer_id, f.name, i.duration_s, i.outcome, i.note FROM dash_incoming i "
                                   "LEFT JOIN dash_farmers f ON f.farmer_id=i.farmer_id ORDER BY i.at DESC LIMIT ?", (limit,)).fetchall()
        return {"ready": self._inbound_ready(), "sync": sync,
                "calls": [{"at": r[0], "number": "******" + r[1], "farmer_id": r[2] or "", "farmer_name": r[3] or "Unknown number",
                           "duration_seconds": r[4] or 0, "outcome": r[5], "note": r[6]} for r in rows]}

    def inbound(self, limit: int = 100) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT i.pushed_at, i.farmer_id, f.name, i.call_date, i.context, i.status, i.note "
                                   "FROM dash_inbound i LEFT JOIN dash_farmers f ON f.farmer_id=i.farmer_id "
                                   "ORDER BY i.pushed_at DESC LIMIT ?", (limit,)).fetchall()
        return [{"at": r[0], "farmer_id": r[1], "farmer_name": r[2] or "", "call_date": r[3], "context": r[4],
                 "status": r[5], "note": r[6]} for r in rows]

    # -- the written message (email) after a call ---------------------------------------------------------------------
    def _message_after_call(self, fid: str, day: date, res: ProviderCallResult, out: dict, weather: dict,
                            more_to_come: bool, callback_time: str = "") -> None:
        """Decides whether the call just stored is followed by a message (docs/DECISIONS.md, 5 Nov and 15 Nov):
        the weather after a call where the farmer understood it, and 'we tried to reach you' plus the weather after the
        last failed attempt, an unanswered call, or a callback that was not picked up. Nothing for a declined farmer, a stop
        request, a provider failure (the team is alerted instead), a call with a retry or callback still to come.
        callback_time ('14:15', 24-hour) is set when this was the call the farmer asked for: the message then says so."""
        try:
            understood = out.get("understood_weather", "")
            if res.status is AttemptStatus.ANSWERED and understood == "yes":
                self._send_message(fid, day, KIND_CALLBACK_WEATHER if callback_time else KIND_WEATHER, weather,
                                   callback_time=callback_time)
            elif more_to_come or out.get("stop_calls_requested") == "yes" or understood == "declined":
                return
            elif res.status in (AttemptStatus.NO_ANSWER, AttemptStatus.BUSY) or (
                    res.status is AttemptStatus.ANSWERED and understood in ("no", "unclear", "no_response")) or (
                    res.status is AttemptStatus.FAILED and res.error == NETWORK_DROP):
                self._send_message(fid, day, KIND_CALLBACK_MISSED if callback_time else KIND_MISSED, weather,
                                   callback_time=callback_time)
        except Exception:                                   # a message problem never disturbs the call results
            pass

    def _send_message(self, fid: str, day: date, kind: str, weather: dict | None = None, callback_time: str = "",
                      record_kind: str = "") -> str:
        """Emails the farmer, once per farmer, day and kind. Never raises. Returns what happened, for the tests and the log."""
        try:
            with self.lock:
                r = self.db.execute("SELECT name,language,village,district,email,consent,active FROM dash_farmers "
                                    "WHERE farmer_id=?", (fid,)).fetchone()
            if not r or not r[5] or not r[6] or self._is_paused(fid):
                return "not sent: farmer not callable"
            rk = record_kind or kind                       # the key a message is recorded under (a test call has its own)
            if rk.startswith("test:") and not self.mail_test_to:
                return "not sent: a test call only emails the test address"
            name, village, district, email = r[0], r[2], r[3], r[4] or ""
            weather = weather or self._saved_weather(fid, day.isoformat())
            now = self._now().isoformat(timespec="seconds")
            with self.lock:                                 # claim first: the primary key stops a second message
                claimed = self.db.execute("INSERT OR IGNORE INTO dash_messages(farmer_id, call_date, kind, channel, status, note, at) VALUES(?,?,?,?,?,?,?)",
                                          (fid, day.isoformat(), rk, "email", "sending", "", now)).rowcount
                self.db.commit()
            if claimed != 1:
                return "not sent: already sent"
            status, note = "sent", ""
            test_to = self.mail_test_to
            if not (email or test_to):
                status, note = "skipped", "no email address for this farmer"
            elif not has_full_weather(weather):
                status, note = "skipped", "weather facts missing"
            else:
                subject, body, html = build_email(name, village or district, weather, kind, callback_time)
                if test_to:
                    subject = f"[Test: {name}, {fid}] {subject}"
                try:
                    self.mailer.send(test_to or email, subject, body, html)
                except MailNotConfigured:
                    status, note = "skipped", "email is not set up (no SMTP settings)"
                except Exception as exc:                    # type only: an error text could quote the address
                    status, note = "failed", _error_detail(exc)
                    self._alert("message_failed", fid, f"The {kind} email could not be sent ({note}).")
            with self.lock:
                self.db.execute("UPDATE dash_messages SET status=?, note=?, at=? WHERE farmer_id=? AND call_date=? AND kind=?",
                                (status, note, self._now().isoformat(timespec="seconds"), fid, day.isoformat(), rk))
                self.db.commit()
            return status
        except Exception as exc:
            return f"error: {type(exc).__name__}"

    def mail_status(self) -> dict:
        """How email is set up, for System Status (never the key, never a full address)."""
        label = getattr(self.mailer, "label", "not configured")
        return {"provider": label, "live": bool(getattr(self.mailer, "live", False)),
                "test_to": mask_email(self.mail_test_to), "test_mode": bool(self.mail_test_to)}

    def send_test_email(self) -> dict:
        """Sends a sample weather email to the test address (GATE0_MAIL_TEST_TO) right now and says what happened, so the
        mail setup can be checked without making a call. Recorded in the Emails table as '(setup test)'."""
        if not self.mail_test_to:
            return {"status": "skipped", "note": "GATE0_MAIL_TEST_TO is not set, so there is nowhere to send a test"}
        subject, body, html = build_email("Test", "your village", {"temp_min": 21, "temp_max": 32, "wind": 14, "rain": 30, "humidity": 65},
                                          KIND_WEATHER)
        status, note = "sent", ""
        try:
            self.mailer.send(self.mail_test_to, f"[Setup test] {subject}", body, html)
        except MailNotConfigured:
            status, note = "skipped", "email is not set up (no GATE0_RESEND_API_KEY and no GATE0_SMTP_HOST on the server)"
        except Exception as exc:                            # type and code only: a message could quote the address
            status, note = "failed", _error_detail(exc)
        now = self._now()
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO dash_messages(farmer_id, call_date, kind, channel, status, note, at) VALUES(?,?,?,?,?,?,?)",
                            ("(setup test)", now.date().isoformat(), f"test:setup:{uuid.uuid4().hex[:8]}", "email", status, note,
                             now.isoformat(timespec="seconds")))
            self.db.commit()
        return {"status": status, "note": note}

    def messages(self, limit: int = 100) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT m.at, m.farmer_id, f.name, m.call_date, m.kind, m.channel, m.status, m.note "
                                   "FROM dash_messages m LEFT JOIN dash_farmers f ON f.farmer_id=m.farmer_id "
                                   "WHERE COALESCE(m.hidden, 0)=0 ORDER BY m.at DESC LIMIT ?", (limit,)).fetchall()
        return [{"key": f"{r[1]}|{r[3]}|{r[4]}", "at": r[0], "farmer_id": r[1], "farmer_name": r[2] or "", "call_date": r[3],
                 "kind": r[4], "channel": r[5], "status": r[6], "note": r[7]} for r in rows]

    def dismiss_messages(self, keys: list | None = None) -> int:
        """Removes email log rows from the list (all of them when keys is None). The rows are kept, only hidden, because
        a row is also what stops the same email going out twice for a farmer and day. Returns how many were hidden."""
        with self.lock:
            if keys is None:
                n = self.db.execute("SELECT COUNT(*) FROM dash_messages WHERE COALESCE(hidden, 0)=0").fetchone()[0]
                self.db.execute("UPDATE dash_messages SET hidden=1")
            else:
                n = 0
                for key in keys:
                    parts = str(key).split("|")
                    if len(parts) != 3:
                        continue
                    n += self.db.execute("SELECT COUNT(*) FROM dash_messages WHERE farmer_id=? AND call_date=? AND kind=? "
                                         "AND COALESCE(hidden, 0)=0", tuple(parts)).fetchone()[0]
                    self.db.execute("UPDATE dash_messages SET hidden=1 WHERE farmer_id=? AND call_date=? AND kind=?", tuple(parts))
            self.db.commit()
        return n

    def transcript_english(self, call_id: str) -> dict:
        """The call's transcript with an English line under each turn, translated through Sarvam and kept so each turn is
        translated once. {available, turns: [{speaker, text, english}], error}."""
        call = self.call(call_id)
        if call is None:
            raise KeyError(call_id)
        turns = [{"speaker": t.get("speaker", ""), "text": t.get("text", "")} for t in call.get("transcript") or []]
        language = call.get("language") or ""
        if self.translator is None:
            return {"available": False, "turns": turns, "error": "Translation is not set up: add SARVAM_API_KEY in Render."}
        if not self.translator.needs_translation(language):
            return {"available": True, "turns": [{**t, "english": t["text"]} for t in turns], "error": ""}
        out, error = [], ""
        for t in turns:
            h = hashlib.sha1(f"{language}|{t['text']}".encode()).hexdigest()
            with self.lock:
                row = self.db.execute("SELECT english FROM dash_translations WHERE h=?", (h,)).fetchone()
            english = row[0] if row else None
            if english is None and not error:
                try:
                    english = self.translator.translate(t["text"], language)
                    with self.lock:
                        self.db.execute("INSERT OR IGNORE INTO dash_translations VALUES(?,?)", (h, english))
                        self.db.commit()
                except Exception as exc:                    # the first failure stops the rest: type and code only
                    error = _error_detail(exc)
            out.append({**t, "english": english or ""})
        return {"available": True, "turns": out, "error": f"Translation failed ({error})" if error else ""}

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
        if self.draining:
            return
        self.recover_interrupted()
        self.recover_live()
        self._daily_inbound_roster()
        self.sync_inbound()
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

    def inbound_loop(self, every: int = 10) -> None:
        """Looks at the calls made to the inbound line every 10 s, on its own, so an incoming call reaches the dashboard soon
        after Sarvam reports it and not at the pace of the slower pass that places retries and callbacks."""
        import time as _t
        while True:
            try:
                if not self.draining:
                    self.sync_inbound()
            except Exception:
                pass
            _t.sleep(every)

    def scheduler_loop(self, every: int = 30) -> None:
        import time as _t
        while True:
            try:
                self.tick()
            except Exception:
                pass
            _t.sleep(every)

    # -- calls that were on the phone when the process stopped (a deploy, a restart, a crash) ------------------------
    def recover_live(self, now: datetime | None = None) -> int:
        """In Queue and In Call rows older than LIVE_RECOVER_MINUTES belong to a process that stopped: a call is given up after
        5 minutes, so nobody is still waiting. For a first call, a hand-placed call or a test call, ask Sarvam what happened and
        save the result as if nothing had happened, so the call log shows it. A call Sarvam has no record of is dropped and the
        team is told (nobody is dialled twice on a guess). A daily send that was cut short is reported once. Retries and callbacks
        that were claimed are recovered by recover_interrupted. Returns how many calls were recovered."""
        now = now or self._now()
        with self.lock:
            try:
                rows = self.db.execute("SELECT farmer_id, call_date, kind, attempt_no, state, since FROM dash_live").fetchall()
            except OperationalError:
                return 0
        limit = timedelta(minutes=LIVE_RECOVER_MINUTES)

        def is_old(since) -> bool:
            try:
                return datetime.fromisoformat(since) + limit < now
            except (TypeError, ValueError):
                return True
        old = [r for r in rows if is_old(r[5])]
        if not old:
            return 0
        recovered, unsent = 0, []
        with self.cb_lock:
            ports = None
            for fid, day, kind, attempt, state, since in old:
                if kind == "callback":                       # its claim in dash_callbacks is recovered by recover_interrupted
                    continue
                if kind == "retry":
                    with self.lock:
                        claimed = self.db.execute("SELECT 1 FROM dash_retries WHERE farmer_id=? AND call_date=? AND status='calling'",
                                                  (fid, day)).fetchone()
                    if claimed:
                        continue
                if state == "queued":
                    if kind == "daily":
                        unsent.append(fid)
                    self._live_clear(fid)
                    continue
                ports = ports or self._make_ports()
                try:
                    recovered += self._recover_call(ports, fid, day, kind, int(attempt or 1), since)
                except Exception:
                    pass                                     # never stops the others; the row is dropped below
                self._live_clear(fid)
        if unsent:
            self._alert("send_interrupted", "", f"Today's send was interrupted by a restart: {len(unsent)} farmers in the queue were "
                                                "not called. Press Send now to call them; farmers already called are skipped.")
        return recovered

    def _recover_call(self, ports: Ports, fid: str, day: str, kind: str, attempt: int, since: str) -> int:
        farmer = ports.farmers.get_context(fid)
        if farmer is None:
            return 0
        found = self._find_call(ports, fid, datetime.fromisoformat(since))
        if found is None:
            if kind != "test":
                self._alert("interrupted_call", fid, "A call was interrupted by a restart and no call was found at the provider. "
                                                     "Use the Call button if the farmer still needs one.")
            return 0
        res, ended = found
        ended = ended.astimezone(self._now().tzinfo or IST)
        out = self._outputs(res)
        if kind == "test":                                   # its own Test row; saved once
            with self.lock:
                seen = self.db.execute("SELECT 1 FROM dash_tests WHERE attempt_id=?", (res.provider_call_id,)).fetchone()
            if seen:
                return 0
            self._save_test(fid, since, res.status.value, res.error, {}, res.provider_call_id, farmer.language.value,
                            res.duration_s or 0, out)
            return 1
        with self.lock:
            done = self.db.execute("SELECT 1 FROM dash_results WHERE farmer_id=? AND call_date=? AND attempt_id=?",
                                   (fid, day, res.provider_call_id)).fetchone()
        if done:                                             # the process saved it just before it stopped
            return 0
        d = date.fromisoformat(day)
        try:
            ports.ledger.record_attempt(CallAttempt(
                farmer_id=fid, call_date=d, attempt_no=attempt, status=res.status, language=farmer.language,
                message_text="(recovered)", provider_call_id=res.provider_call_id, duration_s=res.duration_s,
                error=res.error, weather_source="recovered"))
        except IntegrityError:
            ports.ledger.db.rollback()
        try:
            if attempt == 1:
                ports.ledger.record_day_result(FarmerDayResult(fid, d, final_result(res.status), 1))
            else:
                ports.ledger.db.execute("UPDATE day_results SET result=?, attempts=? WHERE farmer_id=? AND call_date=?",
                                        (final_result(res.status).value, attempt, fid, day))
                ports.ledger.db.commit()
        except Exception:
            ports.ledger.db.rollback()
        self._store_outcome(fid, d, farmer, None, attempt, res, out, at=ended, weather=self._saved_weather(fid, day) or {})
        return 1

    def wait_idle(self, timeout: float = 240.0) -> bool:
        """Waits until no call is on the phone (the daily send, a retry, a callback, a hand-placed call), up to timeout seconds.
        Used when the host asks the process to stop. True when idle."""
        import time as _t
        end = _t.monotonic() + timeout
        while _t.monotonic() < end:
            with self.lock:
                busy = self.running or bool(self._manual)
                try:
                    calling = self.db.execute("SELECT COUNT(*) FROM dash_live WHERE state='calling'").fetchone()[0]
                except OperationalError:
                    calling = 0
            if not busy and not calling:
                return True
            _t.sleep(1)
        return False

    # -- reading results for the dashboard -------------------------------------------------------------------------
    def _all_attempts(self) -> dict[tuple[str, str], list[dict]]:
        """Every attempt, grouped by (farmer, day), in one query (one round trip, however many calls are listed)."""
        with self.lock:
            try:
                rows = self.db.execute("SELECT farmer_id, call_date, attempt_no, status, duration_s, error, message_text FROM attempts "
                                       "ORDER BY farmer_id, call_date, attempt_no").fetchall()
            except OperationalError:
                rows = []
        label = {"answered": "Answered", "no_answer": "No Answer or Rejected", "busy": "Busy", "failed": "Failed"}
        out: dict[tuple[str, str], list[dict]] = {}
        for fid, day, n, status, dur, err, msg in rows:
            out.setdefault((fid, day), []).append({"attempt_number": n, "status": label.get(status, status),
                                                   "duration_seconds": dur or 0, "error_message": err or "",
                                                   "incoming": msg == "(farmer called)"})
        return out

    @staticmethod
    def _status_for(status: str, understood: str, has_callback: bool, retry_pending: bool = False,
                    callback_status: str | None = None, asked_for_callback: bool = False) -> tuple[str, str]:
        """The dashboard's status and disposition for one stored result. asked_for_callback: the agent recorded a time the
        farmer asked to be called back, whether or not a call could be booked for it (a test call books none)."""
        if retry_pending and not has_callback:
            return "Retrying", "Retry scheduled"
        if status == "answered" and asked_for_callback and not has_callback:
            return "Callback Requested", "Callback requested (not booked)"
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
            sms_rows = self.db.execute("SELECT farmer_id, call_date, COUNT(*) FROM dash_messages WHERE status='sent' "
                                       "AND channel='sms' GROUP BY farmer_id, call_date").fetchall()
        retry_due = {(fid, day): due for fid, day, due in rts}
        sms_sent = {(fid, day): n for fid, day, n in sms_rows}        # SMS cost money; email does not, so only SMS is counted
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
                                                        cb[1] if cb else None, bool((cb_text or "").strip()))
            if dash_status == "Callback Requested":
                disposition = f"Callback requested for {cb_text} (not booked: time not understood)"
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
                "call_mode": mode or "", "attempt_id": attempt_id or "", "messages_sent": sms_sent.get((fid, day), 0),
                "direction": "incoming" if attempts and attempts[-1].get("incoming") else "outgoing"})
        out += self._test_rows()
        out += self._incoming_rows()
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
