"""Sarvam AI text to speech (Bulbul). Standard library only; the key comes from SARVAM_API_KEY, never from code.

API: POST https://api.sarvam.ai/text-to-speech, header api-subscription-key, returns base64 WAV in "audios".
Audio is written to GATE0_AUDIO_DIR and the file path is the audio reference handed to telephony.
The same text is synthesised once and reused, so a rerun on the same day costs nothing.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.request
from pathlib import Path

from ..contracts import Language

URL = "https://api.sarvam.ai/text-to-speech"
_CODES = {Language.HI: "hi-IN", Language.EN: "en-IN", Language.KN: "kn-IN"}


class SarvamVoice:
    def __init__(self, api_key: str | None = None, out_dir: str | Path | None = None, model: str | None = None,
                 speaker: str | None = None, sample_rate: int | None = None, opener=urllib.request.urlopen):
        g = os.environ.get
        self._key = api_key or g("SARVAM_API_KEY", "")
        if not self._key:
            raise ValueError("SARVAM_API_KEY is not set (put it in gate0/.env)")
        self.out_dir = Path(out_dir or g("GATE0_AUDIO_DIR", "audio"))
        self.model = model or g("SARVAM_MODEL", "bulbul:v3")
        self.speaker = speaker if speaker is not None else g("SARVAM_SPEAKER", "priya")
        self.sample_rate = int(sample_rate or g("SARVAM_SAMPLE_RATE", 8000))   # 8 kHz suits phone lines
        self._open = opener

    def __repr__(self) -> str:  # keep the key out of any repr or log
        return f"SarvamVoice(model={self.model!r}, speaker={self.speaker!r})"

    def synthesize(self, text: str, language: Language) -> str:
        body = {"text": text, "language_code": _CODES[language], "model": self.model,
                "speech_sample_rate": self.sample_rate}
        if self.speaker:
            body["speaker"] = self.speaker
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
        path = self.out_dir / f"{digest}.wav"
        if path.exists():
            return str(path)
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
            "api-subscription-key": self._key, "Content-Type": "application/json"})
        with self._open(req, timeout=30) as resp:
            audio = base64.b64decode(json.load(resp)["audios"][0])
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return str(path)
