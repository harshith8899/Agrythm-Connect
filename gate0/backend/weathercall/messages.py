"""Builds the written message (email) that follows a call. Pure: farmer name, language and weather in, text out.

Decided 5 Nov 2026 (docs/DECISIONS.md): a fixed template with the four weather facts in the farmer's language and no
free text from the call. Sent after a successful call, and after the last failed attempt or an unanswered or missed
callback, when it also says we tried to reach the farmer. WhatsApp and SMS could not be used, so email carries it
(15 Nov 2026). Hindi, Kannada and Telugu wording is a DRAFT until a native speaker reviews it.
"""
from __future__ import annotations

from .contracts import Language

KIND_WEATHER = "weather"        # the call went through (or the weather was given): the weather facts
KIND_MISSED = "missed"          # we could not reach the farmer: "we tried to reach you" plus the weather facts

# greeting, 'we called' line, 'tried to reach' line, heading, then the four facts and a closing line
_TEXT = {
    Language.EN: dict(
        subject_weather="Today's weather for {place}", subject_missed="We tried to reach you: weather for {place}",
        hello="Hello {name},", tried="We tried to call you from Agrythm but could not reach you.",
        head="Here is today's weather for {place}:", temp="Temperature: {tmin} to {tmax} degrees Celsius",
        wind="Wind speed: up to {wind} km/h", rain="Chance of rain: {rain} percent", hum="Humidity: {humidity} percent",
        bye="This is an automated message from Agrythm. If you do not want these messages, please tell your Agrythm contact person."),
    Language.HI: dict(
        subject_weather="{place} का आज का मौसम", subject_missed="हमने आपसे बात करने की कोशिश की: {place} का मौसम",
        hello="नमस्ते {name} जी,", tried="हमने एग्रिदम की ओर से आपको फ़ोन किया था, लेकिन आपसे बात नहीं हो पाई।",
        head="आज {place} के मौसम की जानकारी:", temp="तापमान: {tmin} से {tmax} डिग्री सेल्सियस",
        wind="हवा की रफ़्तार: {wind} किलोमीटर प्रति घंटा तक", rain="बारिश की संभावना: {rain} प्रतिशत", hum="नमी: {humidity} प्रतिशत",
        bye="यह एग्रिदम का स्वचालित संदेश है। अगर आप ये संदेश नहीं चाहते, तो कृपया अपने एग्रिदम संपर्क व्यक्ति को बता दीजिए।"),
    Language.KN: dict(
        subject_weather="{place} ಇಂದಿನ ಹವಾಮಾನ", subject_missed="ನಾವು ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸಲು ಪ್ರಯತ್ನಿಸಿದೆವು: {place} ಹವಾಮಾನ",
        hello="ನಮಸ್ಕಾರ {name} ಅವರೇ,", tried="ನಾವು ಅಗ್ರಿದಮ್‌ನಿಂದ ನಿಮಗೆ ಕರೆ ಮಾಡಿದ್ದೆವು, ಆದರೆ ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸಲು ಆಗಲಿಲ್ಲ.",
        head="ಇಂದು {place} ಪ್ರದೇಶದ ಹವಾಮಾನ ಮಾಹಿತಿ:", temp="ತಾಪಮಾನ: {tmin} ರಿಂದ {tmax} ಡಿಗ್ರಿ ಸೆಲ್ಸಿಯಸ್",
        wind="ಗಾಳಿಯ ವೇಗ: ಗಂಟೆಗೆ {wind} ಕಿಲೋಮೀಟರ್ ವರೆಗೆ", rain="ಮಳೆ ಬರುವ ಸಾಧ್ಯತೆ: ಶೇಕಡಾ {rain}", hum="ತೇವಾಂಶ: ಶೇಕಡಾ {humidity}",
        bye="ಇದು ಅಗ್ರಿದಮ್‌ನ ಸ್ವಯಂಚಾಲಿತ ಸಂದೇಶ. ಈ ಸಂದೇಶಗಳು ಬೇಡವಾದರೆ, ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಗ್ರಿದಮ್ ಸಂಪರ್ಕ ವ್ಯಕ್ತಿಗೆ ತಿಳಿಸಿ."),
    Language.TE: dict(
        subject_weather="{place} ఈ రోజు వాతావరణం", subject_missed="మేము మిమ్మల్ని సంప్రదించడానికి ప్రయత్నించాము: {place} వాతావరణం",
        hello="నమస్కారం {name} గారు,", tried="మేము అగ్రిథమ్ నుండి మీకు కాల్ చేశాము, కానీ మిమ్మల్ని చేరుకోలేకపోయాము.",
        head="ఈ రోజు {place} ప్రాంతం వాతావరణ సమాచారం:", temp="ఉష్ణోగ్రత: {tmin} నుండి {tmax} డిగ్రీల సెల్సియస్",
        wind="గాలి వేగం: గంటకు {wind} కిలోమీటర్ల వరకు", rain="వర్షం పడే అవకాశం: {rain} శాతం", hum="తేమ: {humidity} శాతం",
        bye="ఇది అగ్రిథమ్ నుండి ఆటోమేటిక్ సందేశం. ఈ సందేశాలు వద్దనుకుంటే, దయచేసి మీ అగ్రిథమ్ సంప్రదింపు వ్యక్తికి చెప్పండి."),
}


def _num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f.is_integer() else f"{f:.1f}"


def build_email(name: str, language: Language, place: str, weather: dict, kind: str) -> tuple[str, str]:
    """(subject, body). weather: temp_min, temp_max, wind, rain, humidity as saved with the call result.
    Only the four weather facts: no advice and nothing the farmer said on the call."""
    t = _TEXT[language]
    f = dict(name=name, place=place, tmin=_num(weather.get("temp_min")), tmax=_num(weather.get("temp_max")),
             wind=_num(weather.get("wind")), rain=_num(weather.get("rain")), humidity=_num(weather.get("humidity")))
    subject = t["subject_missed" if kind == KIND_MISSED else "subject_weather"].format(**f)
    lines = [t["hello"].format(**f), ""]
    if kind == KIND_MISSED:
        lines += [t["tried"], ""]
    lines += [t["head"].format(**f), "- " + t["temp"].format(**f), "- " + t["wind"].format(**f),
              "- " + t["rain"].format(**f), "- " + t["hum"].format(**f), "", t["bye"]]
    return subject, "\n".join(lines)


def has_full_weather(weather: dict) -> bool:
    return all(weather.get(k) not in (None, "") for k in ("temp_min", "temp_max", "wind", "rain", "humidity"))
