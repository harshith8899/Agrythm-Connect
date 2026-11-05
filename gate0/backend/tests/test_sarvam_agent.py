import io
import json
import urllib.parse
from datetime import datetime, timezone

import pytest

from weathercall import ports as P
from weathercall.adapters.sarvam_agent import SarvamAgentTelephony, SarvamAgentVoice, to_e164
from weathercall.contracts import AttemptStatus, Language

ENV = {"SARVAM_AGENT_API_KEY": "sk-agent", "SARVAM_ORG_ID": "org1", "SARVAM_WORKSPACE_ID": "ws1",
       "SARVAM_APP_ID": "app1", "SARVAM_CONNECTION_ID": "conn1", "SARVAM_AGENT_PHONE": "+918000000000",
       "SARVAM_POLL_SECONDS": "10", "SARVAM_CALL_TIMEOUT_SECONDS": "30"}


class FakeSarvam:
    """Answers the create call, then reports the given statuses on successive analytics polls."""
    def __init__(self, statuses):
        self.statuses, self.requests = list(statuses), []

    def __call__(self, req, timeout):
        self.requests.append(req)
        if req.get_method() == "POST":
            return io.BytesIO(json.dumps({"attempt_id": "att-1"}).encode())
        s = self.statuses.pop(0) if self.statuses else None
        items = [] if s is None else [{"attempt_id": "att-1", "connectivity_status": s, "duration_in_seconds": 37.4,
                                       "failure_reason": "NO_FAILURE_REASON", "user_contact": "+919999999999"}]
        return io.BytesIO(json.dumps({"items": items}).encode())


def make(statuses):
    http = FakeSarvam(statuses)
    t = SarvamAgentTelephony(env=ENV, opener=http, sleep=lambda s: None,
                             now=lambda: datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc))
    return t, http


def ref(text="Hello. I am an AI.", lang=Language.EN):
    return SarvamAgentVoice().synthesize(text, lang)


def test_every_language_has_an_agent_name_and_a_tts_code():
    from weathercall.adapters.sarvam import _CODES
    from weathercall.adapters.sarvam_agent import _LANG_NAMES
    for lang in Language:
        assert lang in _LANG_NAMES and lang in _CODES, lang
    assert _LANG_NAMES[Language.TE] == "Telugu" and _CODES[Language.TE] == "te-IN"


def test_telugu_call_asks_sarvam_for_telugu():
    t, http = make([None, "connected"])
    t.place_call("9876543210", ref("నమస్కారం", Language.TE))
    assert json.loads(http.requests[0].data)["app_config"]["app_overrides"] == {"initial_language_name": "Telugu"}


def test_adapters_fit_ports():
    t, _ = make([])
    assert isinstance(t, P.TelephonyProvider) and isinstance(SarvamAgentVoice(), P.VoiceProvider)
    assert "sk-agent" not in repr(t)


def test_call_sends_script_as_first_line_and_maps_answered():
    t, http = make([None, "connected"])
    r = t.place_call("98765 43210", ref("नमस्ते, मैं एआई हूँ", Language.HI))
    assert (r.status, r.duration_s, r.provider_call_id, r.error) == (AttemptStatus.ANSWERED, 37, "att-1", "")
    create = http.requests[0]
    body = json.loads(create.data)
    assert create.full_url.endswith("/outbounds/v1/orgs/org1/workspaces/ws1/outbounds")
    assert create.get_header("X-api-key") == "sk-agent"
    assert body["user_config"]["user_phone_number"] == "+919876543210"
    # the agent's own intro opens the call; Sarvam returns 422 for a variable the agent does not declare
    assert body["app_config"]["app_overrides"] == {"initial_language_name": "Hindi"}
    assert "agent_variables" not in body["app_config"]
    assert body["app_config"]["connection_config"] == {"connection_id": "conn1", "agent_phone_number": "+918000000000"}
    poll = urllib.parse.urlparse(http.requests[1].full_url)
    assert poll.path == "/api/analytics/v1/org1/ws1/app1/attempts"
    assert "att-1" in urllib.parse.parse_qs(poll.query)["filter_conditions"][0]


@pytest.mark.parametrize("status, expected", [("no_answer", AttemptStatus.NO_ANSWER), ("busy", AttemptStatus.BUSY),
                                              ("failed", AttemptStatus.FAILED)])
def test_outcomes_map_to_attempt_status(status, expected):
    t, _ = make([status])
    assert t.place_call("+919876543210", ref()).status is expected


def test_no_outcome_in_time_is_failed_not_answered():
    t, http = make([None, None, None, None])
    r = t.place_call("9876543210", ref())
    assert r.status is AttemptStatus.FAILED and r.error == "outcome_not_reported_in_time"
    assert len(http.requests) == 1 + 3          # one create, polls until the 30 s timeout


def test_results_never_carry_the_phone_number():
    t, _ = make(["connected"])
    assert "9999999999" not in repr(t.place_call("9876543210", ref()))


def test_missing_settings_named_without_values():
    with pytest.raises(ValueError, match="SARVAM_APP_ID"):
        SarvamAgentTelephony(env={k: v for k, v in ENV.items() if k != "SARVAM_APP_ID"})


@pytest.mark.parametrize("raw, out", [("9876543210", "+919876543210"), ("+91 98765 43210", "+919876543210"),
                                      ("919876543210", "+919876543210")])
def test_e164(raw, out):
    assert to_e164(raw) == out


def test_bad_number_rejected():
    with pytest.raises(ValueError):
        to_e164("12345")
