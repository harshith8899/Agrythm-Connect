"""Comprehensive test suite for Sarvam AI Voice and Telephony Adapters."""
from __future__ import annotations

import base64
import json
import urllib.error
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from weathercall import ports as P
from weathercall.adapters.local import InMemoryFarmerSource, SQLiteLedger
from weathercall.adapters.mock import MockWeather
from weathercall.adapters.sarvam import (
    DEFAULT_SPEAKERS, SARVAM_LANG_MAP, SarvamTelephony, SarvamVoice,
)
from weathercall.config import Settings
from weathercall.contracts import (
    AttemptStatus, FarmerContext, Language, WeatherReport,
)
from weathercall.dispatcher import BIDAR_LAT, BIDAR_LON, BIDAR_PLACE, DailyFarmerDispatcher
from weathercall.engine import Ports

RUN_DATE = date(2026, 11, 5)


# 1. Interface conformance
def test_sarvam_adapters_satisfy_ports():
    voice = SarvamVoice()
    telephony = SarvamTelephony()
    assert isinstance(voice, P.VoiceProvider)
    assert isinstance(telephony, P.TelephonyProvider)


# 2. SarvamVoice dry-run mode when no API key
def test_sarvam_voice_dry_run_mode(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.delenv("VOICE_API_KEY", raising=False)

    voice = SarvamVoice(api_key="")
    ref = voice.synthesize("ನಮಸ್ಕಾರ ರೈತ ಮಿತ್ರರೆ", Language.KN)
    assert ref.startswith("sarvam-mock-audio:kn:")


# 3. SarvamVoice successful synthesis for Kannada, Hindi, and English
@pytest.mark.parametrize(
    "lang,expected_code,speaker",
    [
        (Language.KN, "kn-IN", "chetan_kn_conversation"),
        (Language.HI, "hi-IN", "shubh_hi_customer"),
        (Language.EN, "en-IN", "amelia_en_conversational"),
    ],
)
def test_sarvam_voice_synthesize_requests(tmp_path, lang, expected_code, speaker):
    fake_audio_bytes = b"ID3\x03\x00\x00\x00\x00\x00#TSSE\x00\x00\x00"
    fake_b64 = base64.b64encode(fake_audio_bytes).decode("ascii")
    response_json = json.dumps({"audios": [fake_b64]}).encode("utf-8")

    voice = SarvamVoice(
        api_key="test-sarvam-key-123",
        audio_dir=tmp_path,
    )

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_json
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        audio_path = voice.synthesize("Test weather forecast", lang)

        # Verify request parameters
        req: urllib.request.Request = mock_urlopen.call_args[0][0]
        assert req.get_full_url() == "https://api.sarvam.ai/text-to-speech"
        assert req.get_header("Api-subscription-key") == "test-sarvam-key-123"

        payload = json.loads(req.data.decode("utf-8"))
        assert payload["target_language_code"] == expected_code
        assert payload["speaker"] == speaker
        assert payload["model"] == "bulbul:v4-flash"
        assert payload["text"] == "Test weather forecast"

        # Verify audio file written to disk
        assert audio_path.endswith(".mp3")
        with open(audio_path, "rb") as f:
            assert f.read() == fake_audio_bytes


# 4. SarvamVoice error resilience
def test_sarvam_voice_http_error_falls_back():
    voice = SarvamVoice(api_key="invalid-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        err_stream = BytesIO(b'{"error": "Unauthorized key"}')
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.sarvam.ai/text-to-speech",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=err_stream,
        )

        ref = voice.synthesize("Rain chance 20%", Language.EN)
        # Never raises unhandled exception; returns fallback reference
        assert ref.startswith("sarvam-fallback:en:")


# 5. SarvamTelephony dry-run mode when no API key
def test_sarvam_telephony_dry_run():
    telephony = SarvamTelephony(api_key="")
    result = telephony.place_call("9876543210", "audio-ref-1")
    assert result.status == AttemptStatus.ANSWERED
    assert result.provider_call_id.startswith("sarvam-dryrun-")
    assert result.duration_s == 35


# 6. SarvamTelephony live outbound API call
def test_sarvam_telephony_outbound_call_success():
    telephony = SarvamTelephony(
        api_key="test-sarvam-key-123",
        agent_id="agent-agrythm-01",
        outbound_url="https://apps.sarvam.ai/api/outbounds/v1/outbounds",
    )

    api_response = json.dumps({
        "outbound_id": "outbound-sarvam-9999",
        "status": "initiated",
        "duration_s": 38,
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = api_response
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = telephony.place_call("+919999988888", "sarvam-audio-ref")

        assert res.status == AttemptStatus.ANSWERED
        assert res.provider_call_id == "outbound-sarvam-9999"
        assert res.duration_s == 38

        # Inspect request payload
        req: urllib.request.Request = mock_urlopen.call_args[0][0]
        assert req.get_full_url() == "https://apps.sarvam.ai/api/outbounds/v1/outbounds"
        assert req.get_header("Api-subscription-key") == "test-sarvam-key-123"
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["user_phone_number"] == "+919999988888"
        assert payload["app_config"]["app_id"] == "agent-agrythm-01"


# 7. SarvamTelephony status mappings
@pytest.mark.parametrize(
    "sarvam_status,expected_status",
    [
        ("initiated", AttemptStatus.ANSWERED),
        ("answered", AttemptStatus.ANSWERED),
        ("connected", AttemptStatus.ANSWERED),
        ("no_answer", AttemptStatus.NO_ANSWER),
        ("busy", AttemptStatus.BUSY),
        ("failed", AttemptStatus.FAILED),
    ],
)
def test_sarvam_telephony_status_mapping(sarvam_status, expected_status):
    telephony = SarvamTelephony(api_key="key", agent_id="agent")
    api_response = json.dumps({"outbound_id": "call-1", "status": sarvam_status}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = api_response
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = telephony.place_call("+919999900000", "audio-ref")
        assert res.status == expected_status


# 8. SarvamTelephony error handling
def test_sarvam_telephony_network_error_returns_failed():
    telephony = SarvamTelephony(api_key="key", agent_id="agent")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        res = telephony.place_call("+919999900000", "audio-ref")
        assert res.status == AttemptStatus.FAILED
        assert res.error == "URLError"


# 9. Full dispatcher integration with Sarvam Voice & Telephony
def test_dispatcher_with_sarvam_adapters(tmp_path):
    farmers = [
        FarmerContext("F501", "Kallappa", Language.KN, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "9845000001"),
        FarmerContext("F502", "Deepak", Language.HI, BIDAR_PLACE, BIDAR_LAT, BIDAR_LON, True, True, "9845000002"),
    ]
    sarvam_voice = SarvamVoice(api_key="", audio_dir=tmp_path)
    sarvam_telephony = SarvamTelephony(api_key="")

    ports = Ports(
        farmers=InMemoryFarmerSource(farmers),
        ledger=SQLiteLedger(":memory:"),
        weather=MockWeather({BIDAR_PLACE: WeatherReport(BIDAR_PLACE, "partly cloudy", 21, 31, 10, "mock")}),
        voice=sarvam_voice,
        telephony=sarvam_telephony,
    )

    dispatcher = DailyFarmerDispatcher(ports=ports)
    summary = dispatcher.dispatch_daily_calls(call_date=RUN_DATE)

    assert summary.status == "completed"
    assert summary.submitted == 2
    assert summary.failed == 0

    # Verify daily dispatch records
    d1 = ports.ledger.get_daily_dispatch("F501", RUN_DATE)
    d2 = ports.ledger.get_daily_dispatch("F502", RUN_DATE)
    assert d1["status"] == "completed"
    assert d2["status"] == "completed"
    assert d1["provider_call_id"].startswith("sarvam-dryrun-")
    assert d2["provider_call_id"].startswith("sarvam-dryrun-")

