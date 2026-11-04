"""Local stand-ins for the platform: fake farmers and a SQLite ledger. Replaced by Trust AI adapters later."""
from __future__ import annotations

import sqlite3
from datetime import date

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
        f(5, "Manjunath", Language.HI, "Hassan"), f(6, "Geeta", Language.EN, "Mysuru"),
        f(7, "Prakash", Language.HI, "Nowhere"),           # weather missing
        f(8, "Savitha", Language.HI, "Mandya", consent=False),
        f(9, "Basavaraj", Language.HI, "Mysuru", active=False),
        f(10, "Kavya", Language.EN, "Hassan"),
    ]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts(
  farmer_id TEXT, call_date TEXT, attempt_no INT, status TEXT, language TEXT, message_text TEXT,
  provider_call_id TEXT, duration_s INT, error TEXT, weather_source TEXT,
  PRIMARY KEY(farmer_id, call_date, attempt_no));
CREATE TABLE IF NOT EXISTS day_results(
  farmer_id TEXT, call_date TEXT, result TEXT, attempts INT, skip_reason TEXT,
  PRIMARY KEY(farmer_id, call_date));
"""


class SQLiteLedger:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript(_SCHEMA)

    def record_attempt(self, a: CallAttempt) -> None:
        self.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (
            a.farmer_id, a.call_date.isoformat(), a.attempt_no, a.status.value, a.language.value,
            a.message_text, a.provider_call_id, a.duration_s, a.error, a.weather_source))
        self.db.commit()

    def record_day_result(self, r: FarmerDayResult) -> None:
        self.db.execute("INSERT INTO day_results VALUES(?,?,?,?,?)", (
            r.farmer_id, r.call_date.isoformat(), r.result.value, r.attempts,
            r.skip_reason.value if r.skip_reason else None))
        self.db.commit()

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
