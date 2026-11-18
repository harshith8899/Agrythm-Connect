"""English translation of what was said on a call, through Sarvam's text translation API (POST https://api.sarvam.ai/translate,
header api-subscription-key). The key is SARVAM_TRANSLATE_API_KEY, or SARVAM_API_KEY; without one translation is simply not
offered. A translation failure names the HTTP code and Sarvam's error name, never its message (it could quote the text)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

LANGUAGE_CODES = {"hi": "hi-IN", "kn": "kn-IN", "te": "te-IN", "hindi": "hi-IN", "kannada": "kn-IN", "telugu": "te-IN"}
MAX_CHARS = 900                                    # the API takes about 1000 characters at a time


class TranslateError(RuntimeError):
    def __init__(self, safe_text: str):
        super().__init__(safe_text)
        self.safe_text = safe_text


class SarvamTranslator:
    URL = "https://api.sarvam.ai/translate"

    def __init__(self, api_key: str, timeout: float = 20.0, opener=urllib.request.urlopen):
        self._key, self.timeout, self._open = api_key, timeout, opener

    def __repr__(self) -> str:                      # never shows the key
        return "SarvamTranslator()"

    @staticmethod
    def needs_translation(language: str) -> bool:
        return (language or "").strip().lower() in LANGUAGE_CODES

    def translate(self, text: str, language: str) -> str:
        """The English for one turn. English text is returned as it is."""
        code = LANGUAGE_CODES.get((language or "").strip().lower())
        if not code or not text.strip():
            return text
        out = []
        for i in range(0, len(text), MAX_CHARS):
            body = {"input": text[i:i + MAX_CHARS], "source_language_code": code, "target_language_code": "en-IN"}
            req = urllib.request.Request(self.URL, data=json.dumps(body).encode(), method="POST",
                                         headers={"api-subscription-key": self._key, "Content-Type": "application/json",
                                                  "User-Agent": "agrythm-gate0/1.0"})
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    out.append(str(json.load(resp).get("translated_text") or ""))
            except urllib.error.HTTPError as exc:
                name = ""
                try:
                    err = json.load(exc).get("error") or {}
                    name = str(err.get("code") or err.get("type") or "")
                except Exception:
                    pass
                raise TranslateError(f"HTTP {exc.code} {name}".strip()[:80]) from None
        return " ".join(p for p in out if p)


def make_translator(env: dict | None = None):
    e = env if env is not None else os.environ
    key = (e.get("SARVAM_TRANSLATE_API_KEY") or e.get("SARVAM_API_KEY") or "").strip()
    return SarvamTranslator(key) if key else None
