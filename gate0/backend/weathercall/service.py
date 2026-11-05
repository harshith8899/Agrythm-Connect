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
ALREADY_NOTE = "Send skipped: already called today (one call per farmer per day)"
DAILY_RUN_TIME = dtime(9, 0)

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
  understood_weather TEXT, requested_text TEXT, updated_at TEXT, PRIMARY KEY(farmer_id, due_at));
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
            return [r[0] for r in self.db.execute("SELECT farmer_id FROM dash_farmers ORDER BY farmer_id")]

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
            return reason
        farmer, w = prepared.farmer, prepared.weather
        weather = {"temp_min": w.temp_min_c, "temp_max": w.temp_max_c, "wind": w.wind_kmh, "rain": w.rain_chance_pct,
                   "humidity": w.humidity_pct, "source": w.source}
        try:
            res = self.dialler.place(farmer.phone, _LANG_NAMES[farmer.language], self._variables(farmer, w))
        except Exception as exc:                            # provider errors never stop the run; type only
            res = ProviderCallResult(AttemptStatus.FAILED, error=type(exc).__name__)
        self.ports.ledger.record_attempt(CallAttempt(
            farmer_id=fid, call_date=day, attempt_no=1, status=res.status, language=farmer.language,
            message_text=prepared.message, provider_call_id=res.provider_call_id, duration_s=res.duration_s,
            error=res.error, weather_source=w.source))
        self.ports.ledger.record_day_result(FarmerDayResult(fid, day, final_result(res.status), 1))
        out: dict = {}
        if res.status is AttemptStatus.ANSWERED:
            try:
                out = self.dialler.outputs(res.provider_call_id)
            except Exception:
                out = {}
        transcript = [{"speaker": m["speaker"], "text": scrub(m["text"])} for m in out.pop("transcript", None) or []]
        if out.get("call_summary"):
            out["call_summary"] = scrub(out["call_summary"])            # free text: phone-like numbers masked
        self._save(fid, day, status=res.status.value, note=res.error, weather=json.dumps(weather),
                   attempt_id=res.provider_call_id, mode=self.dialler.mode, language=farmer.language.value,
                   duration_s=res.duration_s, transcript=json.dumps(transcript) if transcript else "", **out)
        if out.get("callback_time") and out.get("stop_calls_requested") != "yes":
            self._schedule_callback(fid, day, out["callback_time"])
        return "called"

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
    def _schedule_callback(self, fid: str, source_day: date, text: str, now: datetime | None = None) -> None:
        due = parse_callback(text, now or self._now())
        if due is None:
            return
        in_hours = CALL_FROM <= due.timetz().replace(tzinfo=None) <= CALL_TO
        status, note = ("pending", "") if in_hours else ("skipped", "outside calling hours (5:00 to 22:00 IST)")
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO dash_callbacks VALUES(?,?,?,?,?,?,?,?,?,?)", (
                fid, due.isoformat(timespec="seconds"), source_day.isoformat(), status, note, "", "", "",
                scrub(text)[:60], self._now().isoformat(timespec="seconds")))
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
        if farmer is None or not farmer.active or not farmer.consent or not farmer.phone:
            self._cb_update(fid, due_at, status="skipped", note="not callable (consent, active or phone)")
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
                continue
        out: dict = {}
        if res.status is AttemptStatus.ANSWERED:
            try:
                out = self.dialler.outputs(res.provider_call_id)
            except Exception:
                out = {}
        self._cb_update(fid, due_at, status=res.status.value, note=res.error, attempt_id=res.provider_call_id,
                        call_summary=out.get("call_summary", ""), understood_weather=out.get("understood_weather", ""))
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
        now = self._now()
        if (self.auto_dispatch_enabled() and now.time() >= DAILY_RUN_TIME
                and self._get_setting("last_auto_run_date") != now.date().isoformat() and not self.running):
            self._set_setting("last_auto_run_date", now.date().isoformat())
            self._set_setting("last_auto_run", now.isoformat(timespec="seconds"))
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
        label = {"answered": "Answered", "no_answer": "No Answer", "busy": "Busy", "failed": "Failed"}
        return [{"attempt_number": r[0], "status": label.get(r[1], r[1]), "duration_seconds": r[2] or 0,
                 "error_message": r[3] or ""} for r in rows]

    @staticmethod
    def _status_for(status: str, understood: str, has_callback: bool) -> tuple[str, str]:
        """The dashboard's status and disposition for one stored result."""
        if status == "answered":
            if has_callback:
                return "Callback Scheduled", "Callback Requested"
            if understood == "yes":
                return "Completed", "Weather Delivered"
            return "Not Confirmed", "Heard, not confirmed"
        if status in ("no_answer", "busy"):
            return "Unanswered", "No Answer" if status == "no_answer" else "Busy"
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
        by_day: dict[tuple[str, str], tuple[str, str]] = {}
        for fid, src, due, st in cbs:
            by_day[(fid, src)] = (due, st)
        out = []
        for (fid, day, status, note, weather, attempt_id, mode, lang, dur, summary, cb_text, understood, stop,
             transcript, updated, name, phone, village, district) in rows:
            cb = by_day.get((fid, day))
            dash_status, disposition = self._status_for(status, understood or "", cb is not None)
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
                "note": scrub(note or ""), "retry_count": 0, "duration_seconds": dur or 0,
                "scheduled_callback_time": cb_due.strftime("%d %b, %I:%M %p") if cb_due else None,
                "callback_status": cb[1] if cb else None, "callback_requested_text": cb_text or "",
                "summary": summary or "", "understood_weather": understood or "", "stop_calls_requested": stop or "",
                "transcript": json.loads(transcript) if transcript else [], "attempts_log": self._attempts(fid, day),
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
