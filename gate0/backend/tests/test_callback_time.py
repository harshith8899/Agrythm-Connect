"""The callback the agent recorded must fit the call: the team is told when the agent promised another time than the farmer asked
for, or when the time had already passed (so the callback went to tomorrow)."""
from datetime import date, datetime, timedelta

import pytest

from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST, callback_time_problem

NOW = datetime(2026, 11, 14, 17, 43, tzinfo=IST)
ONE = ("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
       "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Kannada,Yes,Yes\n")


def agent(text, en=None):
    return {"speaker": "Agent", "text": text, **({"en": en} if en else {})}


FARMER = {"speaker": "Farmer", "text": "5:45"}


@pytest.mark.parametrize("callback, said, problem", [
    ("17:45", "Okay, I will call you at 5:30 in the evening.", True),      # the 14 Nov call: asked 5:45, agent said 5:30
    ("17:45", "Okay, I will call you at 5:45 in the evening.", False),
    ("17:45", "Okay, I will call you at 17:45.", False),
    ("17:45", "Okay, I will call you at 5.45 in the evening.", False),
    ("17:45", "Okay, I will call you in the evening. Thank you!", False),   # no clock time spoken: nothing to compare
    ("tomorrow 08:00", "Okay, I will call you tomorrow at 8:00 in the morning.", False),
    ("tomorrow 08:00", "Okay, I will call you tomorrow at 9:00 in the morning.", True),
    ("in 10 minutes", "Okay, I will call you in 10 minutes.", False),
])
def test_the_spoken_time_must_match_the_time_asked_for(callback, said, problem):
    out = callback_time_problem(callback, [agent("hello"), FARMER, agent("ಕನ್ನಡ", said)], NOW)
    assert bool(out) is problem
    if problem:
        assert "confirmed" in out and "set for" in out


def test_only_the_last_thing_the_agent_said_counts():
    turns = [agent("Do you mean 5:30?"), FARMER, agent("Okay, I will call you at 5:45 in the evening.")]
    assert callback_time_problem("17:45", turns, NOW) == ""


def test_a_time_that_had_already_passed_is_reported_once_it_is_moved_to_tomorrow():
    out = callback_time_problem("08:15", [agent("x", "Okay, I will call you at 8:15.")], NOW)
    assert "already passed" in out and "tomorrow" in out and "15 Nov" in out
    assert callback_time_problem("18:15", [agent("x", "Okay, I will call you at 6:15.")], NOW) == ""


def test_no_callback_no_check():
    assert callback_time_problem("", [agent("5:30")], NOW) == ""
    assert callback_time_problem("later", [agent("5:30")], NOW) == ""


def run(tmp_path, callback, said):
    class Speaks:
        mode, live = "speaks", False

        def place(self, *a):
            return ProviderCallResult(AttemptStatus.ANSWERED, provider_call_id="J1", duration_s=30)

        def outputs(self, attempt_id):
            return {"call_summary": "Asked for a call.", "callback_time": callback, "understood_weather": "no_response",
                    "stop_calls_requested": "no", "transcript": [agent("hello"), FARMER, agent("ಕನ್ನಡ", said)]}
    s = DashboardService(str(tmp_path / "c.db"), dialler=Speaks(), env={"GATE0_WEATHER": "mock"}, now=lambda: NOW)
    s.import_csv(ONE)
    s.fire(date(2026, 11, 14))
    return s


def test_the_team_is_told_and_the_callback_is_still_set_for_the_time_asked(tmp_path):
    s = run(tmp_path, "17:45", "Okay, I will call you at 5:30 in the evening.")
    alerts = s.db.execute("SELECT kind, farmer_id, text FROM dash_alerts").fetchall()
    assert len(alerts) == 1 and alerts[0][0] == "callback_time" and alerts[0][1] == "F1" and "5:30" in alerts[0][2]
    cb = s.callbacks()
    assert len(cb) == 1 and cb[0]["due_at"].endswith("17:45:00+05:30")


def test_a_callback_that_matches_raises_no_alert(tmp_path):
    s = run(tmp_path, "17:45", "Okay, I will call you at 5:45 in the evening.")
    assert s.db.execute("SELECT COUNT(*) FROM dash_alerts").fetchone()[0] == 0
    assert len(s.callbacks()) == 1


def test_a_time_that_had_passed_goes_to_tomorrow_and_the_team_is_told(tmp_path):
    s = run(tmp_path, "08:15", "Okay, I will call you at 8:15 in the morning.")
    alerts = s.db.execute("SELECT text FROM dash_alerts").fetchall()
    assert len(alerts) == 1 and "tomorrow" in alerts[0][0]
    assert s.callbacks()[0]["due_at"].startswith("2026-11-15T08:15")
