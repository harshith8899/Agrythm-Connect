"""A call where the farmer says nothing and the agent ends it: shown as no response, not as 'heard, not confirmed'."""
from datetime import date, datetime

from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST

D = date(2026, 11, 19)
T0 = datetime(2026, 11, 19, 9, 0, tzinfo=IST)
CSV = ("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
       "F1,Asha,9876500001,Mandya,Mandya,Karnataka,Hindi,Yes,Yes\n")


class Dial:
    mode, live = "t", False

    def __init__(self, turns, understood=""):
        self.turns, self.understood = turns, understood

    def place(self, phone, language_name, variables):
        return ProviderCallResult(AttemptStatus.ANSWERED, provider_call_id="C1", duration_s=40)

    def outputs(self, attempt_id):
        return {"understood_weather": self.understood, "stop_calls_requested": "", "call_summary": "", "callback_time": "",
                "transcript": self.turns}


def run(tmp_path, dial):
    s = DashboardService(str(tmp_path / "s.db"), dialler=dial, env={"GATE0_WEATHER": "mock"}, now=lambda: T0)
    s.async_inbound = False
    s.import_csv(CSV)
    s.fire(D)
    return s.calls()[0]


def test_a_farmer_who_never_spoke_is_no_response_with_a_plain_summary(tmp_path):
    c = run(tmp_path, Dial([{"speaker": "Agent", "text": "Hello?"}, {"speaker": "Agent", "text": "Are you there?"}]))
    assert c["understood_weather"] == "no_response" and c["status"] == "Retrying"        # silent: the retry rules call again
    assert c["summary"] == "The farmer stayed silent and did not say anything."


def test_a_farmer_who_spoke_but_did_not_confirm_is_still_not_confirmed(tmp_path):
    c = run(tmp_path, Dial([{"speaker": "Agent", "text": "Hello?"}, {"speaker": "Farmer", "text": "hmm"}]))
    assert c["status"] == "Not Confirmed"
