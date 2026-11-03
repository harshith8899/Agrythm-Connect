"""Local stand-ins for the platform: fake farmers and a SQLite ledger. Replaced by Trust AI adapters later."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from ..contracts import (
    CallAttempt, CallStatusView, FarmerContext, FarmerDayResult, FinalResult, Language, SkipReason,
)


class InMemoryFarmerSource:
    def __init__(self, farmers: list[FarmerContext]):
        self._by_id = {f.farmer_id: f for f in farmers}

    def list_callable_ids(self, call_date: date) -> list[str]:
        return list(self._by_id)

    def get_context(self, farmer_id: str) -> FarmerContext | None:
        return self._by_id.get(farmer_id)


def demo_farmers() -> list[FarmerContext]:
    """10 fake farmers. Names and numbers are invented; never put real data in this file."""
    def f(i, name, lang, place, consent=True, active=True, phone=True):
        return FarmerContext(f"F{i:03d}", name, lang, place, 12.5, 76.9, consent, active, f"FAKE-{i:04d}" if phone else "")
    return [
        f(1, "Ramesh", Language.HI, "Mandya"), f(2, "Lakshmi", Language.EN, "Mysuru"),
        f(3, "Suresh", Language.HI, "Hassan"), f(4, "Anita", Language.HI, "Mandya"),
        f(5, "Manjunath", Language.KN, "Hassan"), f(6, "Geeta", Language.EN, "Mysuru"),
        f(7, "Prakash", Language.HI, "Nowhere"),           # weather missing
        f(8, "Savitha", Language.HI, "Mandya", consent=False),
        f(9, "Basavaraj", Language.HI, "Mysuru", active=False),
        f(10, "Kavya", Language.KN, "Hassan"),
    ]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts(
  farmer_id TEXT, call_date TEXT, attempt_no INT, status TEXT, language TEXT, message_text TEXT,
  provider_call_id TEXT, duration_s INT, error TEXT, weather_source TEXT,
  PRIMARY KEY(farmer_id, call_date, attempt_no));
CREATE TABLE IF NOT EXISTS day_results(
  farmer_id TEXT, call_date TEXT, result TEXT, attempts INT, skip_reason TEXT,
  PRIMARY KEY(farmer_id, call_date));
CREATE TABLE IF NOT EXISTS weather(
  place_name TEXT, lat REAL, lon REAL, forecast_date TEXT, summary TEXT, temp_min_c INT, temp_max_c INT,
  rain_chance_pct INT, wind_speed_kmh REAL, humidity_pct INT, source TEXT, fetched_at TEXT,
  PRIMARY KEY(place_name, forecast_date, fetched_at));
CREATE INDEX IF NOT EXISTS idx_weather_lookup ON weather(place_name, forecast_date);
CREATE TABLE IF NOT EXISTS daily_dispatches(
  dispatch_id TEXT PRIMARY KEY,
  farmer_id TEXT NOT NULL,
  dispatch_date TEXT NOT NULL,
  status TEXT NOT NULL,
  provider_call_id TEXT DEFAULT '',
  error TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(farmer_id, dispatch_date)
);
CREATE INDEX IF NOT EXISTS idx_dispatch_date ON daily_dispatches(dispatch_date);
CREATE TABLE IF NOT EXISTS dispatch_locks(
  lock_name TEXT PRIMARY KEY,
  acquired_at TEXT NOT NULL,
  instance_id TEXT NOT NULL
);
"""


class SQLiteLedger:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript(_SCHEMA)
        try:
            columns = [c[1] for c in self.db.execute("PRAGMA table_info(weather)").fetchall()]
            if "forecast_date" not in columns:
                self.db.execute("ALTER TABLE weather ADD COLUMN forecast_date TEXT")
            if "wind_speed_kmh" not in columns:
                self.db.execute("ALTER TABLE weather ADD COLUMN wind_speed_kmh REAL DEFAULT 0.0")
            if "humidity_pct" not in columns:
                self.db.execute("ALTER TABLE weather ADD COLUMN humidity_pct INT DEFAULT 0")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_weather_lookup ON weather(place_name, forecast_date)")
            self.db.commit()
        except Exception:
            pass

    def record_attempt(self, a: CallAttempt) -> None:
        self.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (
            a.farmer_id, a.call_date.isoformat(), a.attempt_no, a.status.value, a.language.value,
            a.message_text, a.provider_call_id, a.duration_s, a.error, a.weather_source))
        self.db.commit()

    def record_day_result(self, r: FarmerDayResult) -> None:
        self.db.execute("INSERT OR REPLACE INTO day_results VALUES(?,?,?,?,?)", (
            r.farmer_id, r.call_date.isoformat(), r.result.value, r.attempts,
            r.skip_reason.value if r.skip_reason else None))
        self.db.commit()

    def record_weather(
        self,
        place_name: str,
        lat: float,
        lon: float,
        summary: str,
        temp_min_c: int,
        temp_max_c: int,
        rain_chance_pct: int,
        source: str,
        fetched_at: str | None = None,
        forecast_date: str | date | None = None,
        wind_speed_kmh: float = 0.0,
        humidity_pct: int = 0,
    ) -> None:
        ts = fetched_at or datetime.now(timezone.utc).isoformat()
        fdate = (
            forecast_date.isoformat()
            if isinstance(forecast_date, date)
            else (forecast_date or ts[:10])
        )
        self.db.execute(
            "INSERT INTO weather(place_name, lat, lon, forecast_date, summary, temp_min_c, temp_max_c, "
            "rain_chance_pct, wind_speed_kmh, humidity_pct, source, fetched_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (place_name, lat, lon, fdate, summary, temp_min_c, temp_max_c, rain_chance_pct, wind_speed_kmh, humidity_pct, source, ts),
        )
        self.db.commit()

    def get_latest_weather(self, place_name: str, forecast_date: str | date | None = None) -> dict[str, Any] | None:
        query = (
            "SELECT place_name, lat, lon, forecast_date, summary, temp_min_c, temp_max_c, rain_chance_pct, wind_speed_kmh, humidity_pct, source, fetched_at "
            "FROM weather WHERE place_name=?"
        )
        params: list[Any] = [place_name]
        if forecast_date:
            fdate = forecast_date.isoformat() if isinstance(forecast_date, date) else forecast_date
            query += " AND forecast_date=?"
            params.append(fdate)
        query += " ORDER BY fetched_at DESC LIMIT 1"
        row = self.db.execute(query, tuple(params)).fetchone()

        if not row:
            return None
        return {
            "place_name": row[0],
            "lat": row[1],
            "lon": row[2],
            "forecast_date": row[3],
            "summary": row[4],
            "temp_min_c": row[5],
            "temp_max_c": row[6],
            "rain_chance_pct": row[7],
            "wind_speed_kmh": row[8],
            "humidity_pct": row[9],
            "source": row[10],
            "fetched_at": row[11],
        }

    def has_final_result(self, farmer_id: str, call_date: date) -> bool:
        row = self.db.execute("SELECT 1 FROM day_results WHERE farmer_id=? AND call_date=?",
                              (farmer_id, call_date.isoformat())).fetchone()
        return row is not None

    def status(self, call_date: date) -> CallStatusView:
        rows = tuple(
            FarmerDayResult(fid, call_date, FinalResult(res), n, SkipReason(sr) if sr else None)
            for fid, res, n, sr in self.db.execute(
                "SELECT farmer_id, result, attempts, skip_reason FROM day_results WHERE call_date=? ORDER BY farmer_id",
                (call_date.isoformat(),)))
        count = lambda r: sum(1 for x in rows if x.result is r)  # noqa: E731
        return CallStatusView(call_date, len(rows), count(FinalResult.ANSWERED), count(FinalResult.UNANSWERED),
                              count(FinalResult.FAILED), count(FinalResult.SKIPPED), rows)

    def has_daily_dispatch(self, farmer_id: str, dispatch_date: date) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM daily_dispatches WHERE farmer_id=? AND dispatch_date=?",
            (farmer_id, dispatch_date.isoformat()),
        ).fetchone()
        return row is not None

    def create_daily_dispatch(
        self,
        farmer_id: str,
        dispatch_date: date,
        status: str,
        provider_call_id: str = "",
        error: str = "",
    ) -> str:
        now_iso = datetime.now(timezone.utc).isoformat()
        dispatch_id = f"disp-{farmer_id}-{dispatch_date.isoformat()}"
        self.db.execute(
            "INSERT INTO daily_dispatches(dispatch_id, farmer_id, dispatch_date, status, provider_call_id, error, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (dispatch_id, farmer_id, dispatch_date.isoformat(), status, provider_call_id, error, now_iso, now_iso),
        )
        self.db.commit()
        return dispatch_id

    def update_daily_dispatch(
        self,
        farmer_id: str,
        dispatch_date: date,
        status: str,
        provider_call_id: str = "",
        error: str = "",
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE daily_dispatches SET status=?, "
            "provider_call_id=CASE WHEN ? != '' THEN ? ELSE provider_call_id END, "
            "error=CASE WHEN ? != '' THEN ? ELSE error END, "
            "updated_at=? WHERE farmer_id=? AND dispatch_date=?",
            (status, provider_call_id, provider_call_id, error, error, now_iso, farmer_id, dispatch_date.isoformat()),
        )
        self.db.commit()

    def get_daily_dispatch(self, farmer_id: str, dispatch_date: date) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT dispatch_id, farmer_id, dispatch_date, status, provider_call_id, error, created_at, updated_at "
            "FROM daily_dispatches WHERE farmer_id=? AND dispatch_date=?",
            (farmer_id, dispatch_date.isoformat()),
        ).fetchone()
        if not row:
            return None
        return {
            "dispatch_id": row[0],
            "farmer_id": row[1],
            "dispatch_date": row[2],
            "status": row[3],
            "provider_call_id": row[4],
            "error": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }

    def acquire_lock(self, lock_name: str, instance_id: str, timeout_seconds: int = 3600) -> bool:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        try:
            self.db.execute(
                "INSERT INTO dispatch_locks(lock_name, acquired_at, instance_id) VALUES(?,?,?)",
                (lock_name, now_iso, instance_id),
            )
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            row = self.db.execute(
                "SELECT acquired_at, instance_id FROM dispatch_locks WHERE lock_name=?",
                (lock_name,),
            ).fetchone()
            if not row:
                return False
            try:
                acquired_dt = datetime.fromisoformat(row[0])
                age_seconds = (now - acquired_dt).total_seconds()
            except Exception:
                age_seconds = timeout_seconds + 1
            if row[1] == instance_id or age_seconds > timeout_seconds:
                self.db.execute(
                    "UPDATE dispatch_locks SET acquired_at=?, instance_id=? WHERE lock_name=?",
                    (now_iso, instance_id, lock_name),
                )
                self.db.commit()
                return True
            return False

    def release_lock(self, lock_name: str, instance_id: str) -> bool:
        cursor = self.db.execute(
            "DELETE FROM dispatch_locks WHERE lock_name=? AND instance_id=?",
            (lock_name, instance_id),
        )
        self.db.commit()
        return cursor.rowcount > 0
