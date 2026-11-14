"""The conversation is saved with Sarvam's English translation of each message, and the call details can show it."""
import json
from datetime import date, datetime

from weathercall.adapters.dialers import SarvamDialler
from weathercall.contracts import AttemptStatus, ProviderCallResult
from weathercall.service import DashboardService, IST

ENV = {"SARVAM_AGENT_API_KEY": "k", "SARVAM_ORG_ID": "o", "SARVAM_WORKSPACE_ID": "w", "SARVAM_APP_ID": "a",
       "SARVAM_CONNECTION_ID": "c", "SARVAM_AGENT_PHONE": "+910000000000"}
IID = "20261114/4b00317f-17:42:32-e99a995b"
ORIGINAL = [{"role": "agent", "text": "ಸರಿ, ನಾನು ನಿಮಗೆ ಸಂಜೆ ಐದೂವರೆ ಗಂಟೆಗೆ ಕರೆ ಮಾಡುತ್ತೇನೆ."}, {"role": "user", "text": "ನನಗೆ 5:45ಕ್ಕೆ ಕಾಲ್ ಮಾಡ್ತೀರಾ?"}]
ENGLISH = [{"role": "agent", "text": "Okay, I will call you at 5:30 in the evening."}, {"role": "user", "text": "Can you call me at 5:45?"}]


def dialler(handler):
    d = SarvamDialler(env=ENV)
    d.urls = []

    def request(url, body=None):
        d.urls.append(url)
        return handler(url)
    d._request = request
    return d


def test_each_message_comes_with_its_english(monkeypatch):
    d = dialler(lambda url: {"items": [{"interaction_id": IID, "original_transcript": ORIGINAL, "translate_transcript": ENGLISH}]})
    got = d._transcript(IID)
    assert got == [{"speaker": "Agent", "text": ORIGINAL[0]["text"], "en": "Okay, I will call you at 5:30 in the evening."},
                   {"speaker": "Farmer", "text": ORIGINAL[1]["text"], "en": "Can you call me at 5:45?"}]
    url = d.urls[0]
    assert "/interactions?" in url and "include_transcript=true" in url and "20261114" not in url.split("start_datetime=")[1][:4]


def test_a_call_in_english_has_no_second_line():
    same = [{"role": "agent", "text": "Hello"}]
    d = dialler(lambda url: {"items": [{"interaction_id": IID, "original_transcript": same, "translate_transcript": same}]})
    assert d._transcript(IID) == [{"speaker": "Agent", "text": "Hello"}]


def test_without_the_interactions_list_the_original_transcript_is_used():
    def handler(url):
        if "/interactions?" in url:
            raise OSError("down")
        return {"messages": [{"role": "assistant", "content": "ಹಲೋ"}, {"role": "user", "content": "ಹೌದು"}]}
    d = dialler(handler)
    assert d._transcript(IID) == [{"speaker": "Agent", "text": "ಹಲೋ"}, {"speaker": "Farmer", "text": "ಹೌದು"}]


def test_an_interaction_that_is_not_in_the_list_falls_back_too():
    def handler(url):
        if "/interactions?" in url:
            return {"items": [{"interaction_id": "other", "original_transcript": ORIGINAL, "translate_transcript": ENGLISH}]}
        return {"messages": [{"role": "assistant", "content": "ಹಲೋ"}]}
    assert dialler(handler)._transcript(IID) == [{"speaker": "Agent", "text": "ಹಲೋ"}]


def test_the_saved_call_keeps_the_english(tmp_path):
    class Speaks:
        mode, live = "speaks", False

        def place(self, *a):
            return ProviderCallResult(AttemptStatus.ANSWERED, provider_call_id="J1", duration_s=29)

        def outputs(self, attempt_id):
            return {"call_summary": "Asked for a call.", "callback_time": "", "understood_weather": "yes", "stop_calls_requested": "no",
                    "transcript": [{"speaker": "Agent", "text": "ಹಲೋ", "en": "Hello"}, {"speaker": "Farmer", "text": "ಹೌದು"}]}
    s = DashboardService(str(tmp_path / "e.db"), dialler=Speaks(), env={"GATE0_WEATHER": "mock"},
                         now=lambda: datetime(2026, 11, 14, 17, 42, tzinfo=IST))
    s.import_csv("Farmer ID,Farmer Name,Mobile Number,Village,District,State,Preferred Calling Language,Call Consent,Active\n"
                 "F1,Ramesh,9876543210,Mandya,Mandya,Karnataka,Kannada,Yes,Yes\n")
    s._test_call("F1")
    s.fire(date(2026, 11, 14))
    rows = {c["call_id"].split("-")[0][:4]: c for c in s.calls()}
    for row in s.calls():
        assert row["transcript"][0] == {"speaker": "Agent", "text": "ಹಲೋ", "en": "Hello"}
        assert "en" not in row["transcript"][1]
    assert len(s.calls()) == 2 and rows
