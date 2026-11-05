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
from .adapters.open_meteo import OpenMeteoWeather, geocode
from .adapters.sarvam_agent import _LANG_NAMES
from .adapters.sarvam_campaign import IST, scrub
from .adapters.sheet import _ALIASES, _key, _read_rows, load_farmers
from .adapters.weather_store import StoredWeather
from .config import Settings
from .contracts import (AttemptStatus, CallAttempt, CallRequest, FarmerContext, FarmerDayResult, Language,
                        ProviderCallResult)
from .engine import Ports, final_result, prepare_call
from .script import format_now, weather_variables

CALL_FROM, CALL_TO = dtime(5, 0), dtime(22, 0)   # callbacks only inside these hours (IST), set by the team on 5 Nov
GRACE_MINUTES = 30        # a callback not placed within this long after its time is marked missed, not called late
MAX_RELATIVE_MINUTES = 12 * 60
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
CREATE TABLE IF NOT EXISTS dash_paused(farmer_id TEXT PRIMARY KEY, since TEXT);
CREATE TABLE IF NOT EXISTS dash_alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, farmer_id TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS dash_retries(
  farmer_id TEXT, call_date TEXT, attempt_no INT, due_at TEXT, status TEXT, note TEXT,
  PRIMARY KEY(farmer_id, call_date, attempt_no));
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
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript(_SCHEMA)
        try:                                                    # databases made before the reschedule limit
            self.db.execute("ALTER TABLE dash_callbacks ADD COLUMN reschedules INT DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        self.settings = Settings.from_env()
        self.dialler, self.note = (dialler, note) if dialler else make_dialler(env)
        e = env if env is not None else os.environ
        self.real_weather = e.get("GATE0_WEATHER", "open_meteo") != "mock"
        self._weather = weather or (OpenMeteoWeather() if self.real_weather else MockWeather())
        self.ports: Ports | None = None      # engine connections are made inside the working thread (SQLite is per thread)
        self.running = False
        self.last_run: dict | None = None
        self.cb_lock = threading.Lock()

    def _make_ports(self) -> Ports:
        return Ports(DBFarmers(self.db, self.lock), SQLiteLedger(self.db_path), StoredWeather(
            self._weather, self.db_path, sleep=lambda s: None),       # no long retry waits behind a button
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
                "note": self.note, "weatherSource": "open-meteo (real)" if self.real_weather else "mock",
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

    def farmers(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT farmer_id,name,phone,language,village,district,state,lat,lon,consent,active "
                                   "FROM dash_farmers ORDER BY farmer_id").fetchall()
        return [{"farmer_id": r[0], "farmer_name": r[1], "phone_number": mask_phone(r[2]),
                 "preferred_language": _LANG_LABELS[Language(r[3])], "village": r[4], "district": r[5], "state": r[6],
                 "located": bool(r[7] or r[8]), "call_consent": "Yes" if r[9] else "No", "active": "Yes" if r[10] else "No"}
                for r in rows]

    # -- sending the day's calls ---------------------------------------------------------------------------------
    def _save(self, fid: str, day: date, **kw) -> None:
        cols = ["status", "note", "weather", "attempt_id", "mode", "language", "duration_s", *OUTPUT_VARS, "transcript"]
        vals = [kw.get(c, "") for c in cols]
        with self.lock:
            self.db.execute(f"INSERT OR REPLACE INTO dash_results VALUES(?,?,{','.join('?' * len(cols))},?)",
                            (fid, day.isoformat(), *vals, self._now().isoformat(timespec="seconds")))
            self.db.commit()

    def _variables(self, farmer: FarmerContext, w) -> dict:
        # only variables the agent declares (Sarvam returns 422 otherwise); now_text lets it confirm callback days
        return weather_variables(farmer, w, format_now(self._now()))

    def fire_one(self, fid: str, day: date) -> str:
        prepared = prepare_call(CallRequest(fid, day), self.ports, self.settings)
        if isinstance(prepared, FarmerDayResult):
            reason = prepared.skip_reason.value if prepared.skip_reason else prepared.result.value
            if reason == "already_called_today":           # keep the earlier real result, just say why nothing new happened
                with self.lock:
                    row = self.db.execute("SELECT status, note FROM dash_results WHERE farmer_id=? AND call_date=?",
                                          (fid, day.isoformat())).fetchone()
                    if row and row[0] == "skipped":         # skipped earlier: keep its own reason (no consent, ...)
                        return row[1] or reason
                    self.db.execute("UPDATE dash_results SET note=? WHERE farmer_id=? AND call_date=?",
                                    (ALREADY_NOTE, fid, day.isoformat()))
                    self.db.commit()
            else:
                self._save(fid, day, status="skipped", note=reason, mode=self.dialler.mode)
                if reason == "weather_unavailable":
                    self._alert("weather_unavailable", fid, "No weather for this farmer today, so no call was made.")
            return reason
        farmer, w = prepared.farmer, prepared.weather
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
                       res: ProviderCallResult, out: dict) -> None:
        """Keeps the latest attempt's result for the dashboard, then plans a callback or a retry if one is due."""
        weather = {"temp_min": w.temp_min_c, "temp_max": w.temp_max_c, "wind": w.wind_kmh, "rain": w.rain_chance_pct,
                   "humidity": w.humidity_pct, "source": w.source}
        transcript = [{"speaker": m["speaker"], "text": scrub(m["text"])} for m in out.pop("transcript", None) or []]
        if out.get("call_summary"):
            out["call_summary"] = scrub(out["call_summary"])            # free text: phone-like numbers masked
        self._save(fid, day, status=res.status.value, note=res.error, weather=json.dumps(weather),
                   attempt_id=res.provider_call_id, mode=self.dialler.mode, language=farmer.language.value,
                   duration_s=res.duration_s, transcript=json.dumps(transcript) if transcript else "", **out)
        if out.get("stop_calls_requested") == "yes":
            self._note_stop(fid, day)
        if out.get("callback_time") and out.get("stop_calls_requested") != "yes":
            self._schedule_callback(fid, day, out["callback_time"])
        if not self._plan_retry(fid, day, attempt_no, res.status, out) and res.status is AttemptStatus.FAILED:
            self._alert("provider_failure", fid,
                        f"The call failed and will not be retried ({scrub(res.error or 'provider error')[:80]}).")

    # -- retries: 3 attempts, 30 min then 1 hour; a farmer who asked for a callback or to stop is not retried ----------
    def _has_callback(self, fid: str, day: date) -> bool:
        with self.lock:
            return self.db.execute("SELECT 1 FROM dash_callbacks WHERE farmer_id=? AND source_date=?",
                                   (fid, day.isoformat())).fetchone() is not None

    def _plan_retry(self, fid: str, day: date, attempt_no: int, status: AttemptStatus, out: dict) -> bool:
        """Plans the next attempt; False when none is due (so the caller can alert on a failed call)."""
        if self._has_callback(fid, day) or out.get("stop_calls_requested") == "yes":
            return False
        if status in (AttemptStatus.NO_ANSWER, AttemptStatus.BUSY) or (
                status is AttemptStatus.ANSWERED and out.get("understood_weather") in ("no", "unclear")):
            gaps = RETRY_GAPS_MIN              # not picked up, rejected, busy, or heard but never confirmed
        elif status is AttemptStatus.FAILED:
            gaps = FAILURE_RETRY_GAPS_MIN
        else:
            return False
        if attempt_no >= self.settings.max_attempts or attempt_no > len(gaps):
            return False
        due = self._now() + timedelta(minutes=gaps[attempt_no - 1])
        if due.date() != day or not (CALL_FROM <= due.timetz().replace(tzinfo=None) <= CALL_TO):
            return False                       # a retry never runs after the calling window or on another day
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO dash_retries VALUES(?,?,?,?,?,?)", (
                fid, day.isoformat(), attempt_no + 1, due.isoformat(timespec="seconds"), "pending", ""))
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
                if datetime.fromisoformat(due_at) < now - timedelta(minutes=GRACE_MINUTES):
                    self._retry_update(fid, day, attempt_no, "missed", f"not placed within {GRACE_MINUTES} min")
                    continue
                self._retry_update(fid, day, attempt_no, "calling")
                try:
                    outcome = self._retry_one(ports, fid, date.fromisoformat(day), attempt_no)
                except Exception as exc:
                    outcome = f"error: {type(exc).__name__}"
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
        res, out = self._place(farmer, w)
        try:
            ports.ledger.record_attempt(CallAttempt(
                farmer_id=fid, call_date=day, attempt_no=attempt_no, status=res.status, language=farmer.language,
                message_text="(retry)", provider_call_id=res.provider_call_id, duration_s=res.duration_s,
                error=res.error, weather_source=w.source))
        except sqlite3.IntegrityError:
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
            for fid in self.ports.farmers.list_callable_ids(day):
                try:
                    outcome = self.fire_one(fid, day)
                except Exception as exc:                    # one farmer never stops the others
                    self._save(fid, day, status="error", note=type(exc).__name__, mode=self.dialler.mode)
                    outcome = "error"
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
                if datetime.fromisoformat(due_at) < now - timedelta(minutes=GRACE_MINUTES):
                    self._cb_update(fid, due_at, status="missed",
                                    note=f"not placed within {GRACE_MINUTES} min of the requested time")
                    continue
                self._cb_update(fid, due_at, status="calling")
                try:
                    placed += self._callback_one(ports, fid, due_at, date.fromisoformat(source_date))
                except Exception as exc:                    # never retried, never stops the others
                    self._cb_update(fid, due_at, status="error", note=type(exc).__name__)
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
        try:
            res = self.dialler.place(farmer.phone, _LANG_NAMES[farmer.language], self._variables(farmer, w))
        except Exception as exc:
            res = ProviderCallResult(AttemptStatus.FAILED, error=type(exc).__name__)
        for n in (1, 2, 3):                                 # a free attempt number for that day
            try:
                ports.ledger.record_attempt(CallAttempt(
                    farmer_id=fid, call_date=due_day, attempt_no=n, status=res.status, language=farmer.language,
                    message_text="(callback)", provider_call_id=res.provider_call_id, duration_s=res.duration_s,
                    error=res.error, weather_source=w.source))
                if due_day != source_day:                   # a new day: this call is that day's one call
                    ports.ledger.record_day_result(FarmerDayResult(fid, due_day, final_result(res.status), 1))
                break
            except sqlite3.IntegrityError:
                ports.ledger.db.rollback()
                continue
        out: dict = {}
        if res.status is AttemptStatus.ANSWERED:
            try:
                out = self.dialler.outputs(res.provider_call_id)
            except Exception:
                out = {}
        self._cb_update(fid, due_at, status=res.status.value, note=res.error, attempt_id=res.provider_call_id,
                        call_summary=out.get("call_summary", ""), understood_weather=out.get("understood_weather", ""))
        if out.get("stop_calls_requested") == "yes":
            self._note_stop(fid, due_day)
        elif out.get("callback_time"):                      # asked to be called later again: allowed twice at most
            with self.lock:
                used = self.db.execute("SELECT reschedules FROM dash_callbacks WHERE farmer_id=? AND due_at=?",
                                       (fid, due_at)).fetchone()[0] or 0
            if used < MAX_RESCHEDULES:
                self._schedule_callback(fid, source_day, out["callback_time"], reschedules=used + 1)
            else:
                self._alert("callback_limit", fid,
                            f"Asked to move the callback again after {MAX_RESCHEDULES} reschedules; no more callbacks.")
        return 1

    def callbacks(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT c.farmer_id, f.name, c.due_at, c.status, c.note, c.call_summary, "
                                   "c.understood_weather, c.requested_text FROM dash_callbacks c "
                                   "LEFT JOIN dash_farmers f ON f.farmer_id=c.farmer_id ORDER BY c.due_at DESC").fetchall()
        keys = ("farmer_id", "farmer_name", "due_at", "status", "note", "summary", "understood", "asked")
        return [dict(zip(keys, r)) for r in rows]

    # -- the background timer: callbacks when due, and the daily send when switched on ------------------------------
    def tick(self) -> None:
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
    def _attempts(self, fid: str, call_date: str) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT attempt_no, status, duration_s, error FROM attempts WHERE farmer_id=? "
                                "AND call_date=? ORDER BY attempt_no", (fid, call_date)).fetchall()
        except sqlite3.OperationalError:
            rows = []
        finally:
            conn.close()
        label = {"answered": "Answered", "no_answer": "No Answer or Rejected", "busy": "Busy", "failed": "Failed"}
        return [{"attempt_number": r[0], "status": label.get(r[1], r[1]), "duration_seconds": r[2] or 0,
                 "error_message": r[3] or ""} for r in rows]

    @staticmethod
    def _status_for(status: str, understood: str, has_callback: bool, retry_pending: bool = False) -> tuple[str, str]:
        """The dashboard's status and disposition for one stored result."""
        if retry_pending and not has_callback:
            return "Retrying", "Retry scheduled"
        if status == "answered":
            if has_callback:
                return "Callback Scheduled", "Callback Requested"
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
        by_day: dict[tuple[str, str], tuple[str, str]] = {}
        for fid, src, due, st in cbs:
            by_day[(fid, src)] = (due, st)
        out = []
        for (fid, day, status, note, weather, attempt_id, mode, lang, dur, summary, cb_text, understood, stop,
             transcript, updated, name, phone, village, district) in rows:
            cb = by_day.get((fid, day))
            retry_at = retry_due.get((fid, day))
            dash_status, disposition = self._status_for(status, understood or "", cb is not None, retry_at is not None)
            attempts = self._attempts(fid, day)
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
                "attempts_used": len(attempts), "max_attempts": self.settings.max_attempts,
                "next_attempt_at": datetime.fromisoformat(retry_at).strftime("%d %b, %I:%M %p") if retry_at else None,
                "scheduled_callback_time": cb_due.strftime("%d %b, %I:%M %p") if cb_due else None,
                "callback_status": cb[1] if cb else None, "callback_requested_text": cb_text or "",
                "summary": summary or "", "understood_weather": understood or "", "stop_calls_requested": stop or "",
                "transcript": json.loads(transcript) if transcript else [], "attempts_log": attempts,
                "call_mode": mode or "", "attempt_id": attempt_id or ""})
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
