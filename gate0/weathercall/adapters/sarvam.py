"""Sarvam AI Voice and Telephony Adapters for Agrythm Connect.

Integrates Sarvam AI's:
1. Bulbul Text-to-Speech API (v4 Flash / v3) for high-accuracy Indic speech synthesis
   (Kannada 'kn-IN', Hindi 'hi-IN', and English 'en-IN').
2. Samvaad Voice Agent / Outbound Calling platform to initiate automated calls to farmers.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import pathlib
import urllib.error
import urllib.request
from typing import Any

from ..config import load_env
from ..contracts import AttemptStatus, Language, ProviderCallResult

logger = logging.getLogger("weathercall.sarvam")

# Default API Endpoints
_DEFAULT_TTS_URL = "https://api.sarvam.ai/text-to-speech"
_DEFAULT_OUTBOUND_URL = "https://apps.sarvam.ai/api/outbounds/v1/outbounds"

# BCP-47 Language Code Mapping for Sarvam AI
SARVAM_LANG_MAP: dict[Language, str] = {
    Language.KN: "kn-IN",
    Language.HI: "hi-IN",
    Language.EN: "en-IN",
}

# Recommended native voice personas for Bulbul models
DEFAULT_SPEAKERS_V4: dict[Language, str] = {
    Language.KN: "chetan_kn_conversation",
    Language.HI: "shubh_hi_customer",
    Language.EN: "amelia_en_conversational",
}

DEFAULT_SPEAKERS_V3: dict[Language, str] = {
    Language.KN: "meera",
    Language.HI: "shubh",
    Language.EN: "meera",
}
DEFAULT_SPEAKERS = DEFAULT_SPEAKERS_V4


class SarvamVoice:
    """Adapter for Sarvam AI's Bulbul Text-to-Speech API.

    Satisfies the `VoiceProvider` protocol in `weathercall.ports`.
    Converts weather advisory text into natural Indic speech for Kannada, Hindi, and English.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        audio_dir: str | pathlib.Path | None = None,
        pace: float = 1.0,
        sample_rate: int = 8000,
    ) -> None:
        load_env()
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("SARVAM_API_KEY") or os.environ.get("VOICE_API_KEY", "")
        self.base_url = (
            base_url
            or os.environ.get("SARVAM_TTS_URL")
            or _DEFAULT_TTS_URL
        )
        self.model = model or os.environ.get("SARVAM_MODEL", "bulbul:v4-flash")
        self.pace = float(os.environ.get("SARVAM_PACE", pace))
        self.sample_rate = int(os.environ.get("SARVAM_SAMPLE_RATE", sample_rate))

        if audio_dir is None:
            here = pathlib.Path(__file__).resolve().parent.parent.parent
            self.audio_dir = here / "data" / "audio"
        else:
            self.audio_dir = pathlib.Path(audio_dir)

    def synthesize(self, text: str, language: Language) -> str:
        """Synthesize text into speech and return an audio reference (filepath or URI)."""
        lang_code = SARVAM_LANG_MAP.get(language, "en-IN")
        default_map = DEFAULT_SPEAKERS_V4 if "v4" in self.model else DEFAULT_SPEAKERS_V3
        speaker = (
            os.environ.get(f"SARVAM_SPEAKER_{language.value.upper()}")
            or default_map.get(language, "chetan_kn_conversation")
        )

        # If no API key configured (development/dry-run mode), return fallback audio reference
        if not self.api_key:
            logger.warning(
                f"[SARVAM-TTS] SARVAM_API_KEY is not set. Generating mock audio reference for {lang_code}."
            )
            return f"sarvam-mock-audio:{language.value}:{abs(hash(text)) % 10**8}"

        payload = {
            "text": text,
            "target_language_code": lang_code,
            "speaker": speaker,
            "model": self.model,
            "pace": self.pace,
            "speech_sample_rate": self.sample_rate,
            "audio_format": "mp3",
        }

        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "api-subscription-key": self.api_key,
                "User-Agent": "Agrythm-Connect-Gate0/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                body = response.read().decode("utf-8")
                data = json.loads(body)
                audios = data.get("audios", [])
                if not audios:
                    logger.error("[SARVAM-TTS] Empty audio list received from Sarvam TTS API.")
                    return f"sarvam-fallback:{language.value}:{abs(hash(text)) % 10**8}"

                raw_audio = base64.b64decode(audios[0])
                self.audio_dir.mkdir(parents=True, exist_ok=True)
                audio_filename = f"sarvam_{language.value}_{abs(hash(text)) % 10**8}.mp3"
                audio_path = self.audio_dir / audio_filename
                audio_path.write_bytes(raw_audio)
                logger.info(f"[SARVAM-TTS] Synthesized audio saved: {audio_path}")
                return str(audio_path)

        except urllib.error.HTTPError as exc:
            err_msg = exc.read().decode("utf-8", errors="ignore")
            logger.error(f"[SARVAM-TTS] HTTP {exc.code} error from Sarvam TTS: {err_msg}")
            return f"sarvam-fallback:{language.value}:{abs(hash(text)) % 10**8}"
        except Exception as exc:
            logger.error(f"[SARVAM-TTS] Unexpected error during synthesis: {exc}", exc_info=True)
            return f"sarvam-fallback:{language.value}:{abs(hash(text)) % 10**8}"


class SarvamTelephony:
    """Adapter for Sarvam AI's Voice Agent / Outbound Telephony API.

    Satisfies the `TelephonyProvider` protocol in `weathercall.ports`.
    Places automated outbound voice calls to farmers using Sarvam AI's Samvaad platform.
    """

    def __init__(
        self,
        api_key: str | None = None,
        outbound_url: str | None = None,
        agent_id: str | None = None,
        org_id: str | None = None,
        workspace_id: str | None = None,
        script: dict[str, list[AttemptStatus]] | None = None,
    ) -> None:
        load_env()
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("SARVAM_API_KEY") or os.environ.get("TELEPHONY_API_KEY", "")
        if agent_id is not None:
            self.agent_id = agent_id
        else:
            self.agent_id = os.environ.get("SARVAM_AGENT_ID") or os.environ.get("SARVAM_APP_ID", "")
        self.org_id = org_id or os.environ.get("SARVAM_ORG_ID", "")
        self.workspace_id = workspace_id or os.environ.get("SARVAM_WORKSPACE_ID", "")
        self.connection_id = os.environ.get("SARVAM_CONNECTION_ID", "")
        self.from_number = os.environ.get("TELEPHONY_FROM_NUMBER") or os.environ.get("SARVAM_FROM_NUMBER", "")
        self.outbound_url = outbound_url or os.environ.get("SARVAM_OUTBOUND_URL", _DEFAULT_OUTBOUND_URL)
        self.script = script or {}
        self._counts: dict[str, int] = {}

    def place_call(self, phone: str, audio_ref: str) -> ProviderCallResult:
        """Trigger an automated voice agent call to the farmer's registered phone number."""
        i = self._counts.get(phone, 0)
        self._counts[phone] = i + 1

        # 1. Scripted mock mode for testing
        if phone in self.script:
            outcomes = self.script[phone]
            status = outcomes[min(i, len(outcomes) - 1)]
            ok = status is AttemptStatus.ANSWERED
            return ProviderCallResult(
                status=status,
                provider_call_id=f"sarvam-script-{abs(hash(phone)) % 10**6}-{i + 1}",
                duration_s=35 if ok else 0,
                error="" if status is not AttemptStatus.FAILED else "mock_sarvam_failure",
            )

        # 2. Dry-run mode if API key or Agent ID is not configured
        if not self.api_key or not self.agent_id:
            logger.info(
                f"[SARVAM-TELEPHONY] Dispatching call to {phone} using audio '{audio_ref}'. "
                "Simulated telephony response recorded (SARVAM_AGENT_ID not set)."
            )
            return ProviderCallResult(
                status=AttemptStatus.ANSWERED,
                provider_call_id=f"sarvam-dryrun-{abs(hash(phone)) % 10**6}-{i + 1}",
                duration_s=35,
            )

        # 3. Live Sarvam Outbound API call
        endpoint = self.outbound_url
        if self.org_id and self.workspace_id and ":org_id" in endpoint:
            endpoint = endpoint.replace(":org_id", self.org_id).replace(":workspace_id", self.workspace_id)

        app_config: dict[str, Any] = {
            "app_id": self.agent_id,
            "app_version": 1,
        }
        if self.connection_id or self.from_number:
            conn_cfg: dict[str, Any] = {}
            if self.connection_id:
                conn_cfg["connection_id"] = self.connection_id
            if self.from_number:
                conn_cfg["agent_phone_number"] = self.from_number
            app_config["connection_config"] = conn_cfg

        payload: dict[str, Any] = {
            "user_phone_number": phone,
            "user_config": {
                "user_phone_number": phone,
            },
            "app_config": app_config,
            "variables": {
                "audio_ref": audio_ref,
                "call_purpose": "weather_advisory",
                "location": "Bidar",
            },
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
                "api-subscription-key": self.api_key,
                "User-Agent": "Agrythm-Connect-Gate0/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                res_data = json.loads(body)
                outbound_id = (
                    res_data.get("outbound_id")
                    or res_data.get("call_id")
                    or res_data.get("id")
                    or f"sarvam-{abs(hash(phone)) % 10**6}"
                )
                raw_status = str(res_data.get("status", "initiated")).lower()

                # Map Sarvam status to AttemptStatus
                if raw_status in ("answered", "completed", "connected", "initiated", "queued", "in_progress"):
                    status = AttemptStatus.ANSWERED
                elif raw_status in ("no_answer", "unanswered", "timeout"):
                    status = AttemptStatus.NO_ANSWER
                elif raw_status in ("busy",):
                    status = AttemptStatus.BUSY
                else:
                    status = AttemptStatus.FAILED

                return ProviderCallResult(
                    status=status,
                    provider_call_id=str(outbound_id),
                    duration_s=int(res_data.get("duration_s", 35)),
                    error=res_data.get("error", ""),
                )
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="ignore")
            logger.error(f"[SARVAM-TELEPHONY] HTTP {exc.code} calling {phone}: {err}")
            return ProviderCallResult(
                status=AttemptStatus.FAILED,
                error=f"HTTP_{exc.code}",
            )
        except Exception as exc:
            logger.error(f"[SARVAM-TELEPHONY] Exception placing call to {phone}: {exc}", exc_info=True)
            return ProviderCallResult(
                status=AttemptStatus.FAILED,
                error=type(exc).__name__,
            )

