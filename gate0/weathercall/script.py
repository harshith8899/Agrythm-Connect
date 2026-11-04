"""Builds the spoken message. Pure function: weather + farmer in, text out. No provider calls.

The message greets the farmer by name, gives today's temperature, wind, chance of rain and humidity (nothing
else) for their village or district, and asks whether it was understood. It does not announce that the voice is an
AI (team decision, 2 Nov 2026); the agent answers honestly if asked. Hindi, Kannada and Telugu are plain spoken language,
because the farmers understand only their local language.
Hindi, Kannada and Telugu wording is a DRAFT and needs native-speaker review (see docs/DECISIONS.md).
"""
from __future__ import annotations

from .contracts import FarmerContext, Language, WeatherReport

WORDS_PER_SECOND = 2.4  # rough speaking pace; replaced by real measured length once TTS is connected

_EN = (
    "Hello {name}. This is an automated weather call from Agrythm. "
    "Here is today's weather for {place}. "
    "The temperature will be between {tmin} and {tmax} degrees Celsius. "
    "The wind speed will be up to {wind} kilometres per hour. "
    "The chance of rain is {rain} percent. "
    "The humidity in the air will be {humidity} percent. "
    "I will call every morning like this with the weather. "
    "If you do not want these calls, please tell your Agrythm contact person. "
    "Did you understand this weather information? Please say yes or no."
)

_HI = (
    "नमस्ते {name} जी। मैं एग्रिदम की ओर से मौसम बताने के लिए फ़ोन कर रही हूँ। "
    "आज {place} इलाके के मौसम की जानकारी यह है। "
    "तापमान {tmin} से {tmax} डिग्री के बीच रहेगा। "
    "हवा की रफ़्तार {wind} किलोमीटर प्रति घंटा तक रहेगी। "
    "बारिश होने की संभावना {rain} प्रतिशत है। "
    "हवा में नमी {humidity} प्रतिशत रहेगी। "
    "मैं हर सुबह इसी तरह मौसम बताने के लिए फ़ोन करूँगी। "
    "अगर आप ये फ़ोन नहीं चाहते, तो कृपया अपने एग्रिदम संपर्क व्यक्ति को बता दीजिए। "
    "क्या आपको यह मौसम की जानकारी समझ आई? कृपया हाँ या ना बताइए।"
)

_KN = (
    "ನಮಸ್ಕಾರ {name} ಅವರೇ. ನಾನು ಅಗ್ರಿದಮ್‌ನಿಂದ ಹವಾಮಾನ ತಿಳಿಸಲು ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ. "
    "ಇಂದು {place} ಪ್ರದೇಶದ ಹವಾಮಾನ ಮಾಹಿತಿ ಇದು. "
    "ತಾಪಮಾನ {tmin} ರಿಂದ {tmax} ಡಿಗ್ರಿ ನಡುವೆ ಇರುತ್ತದೆ. "
    "ಗಾಳಿಯ ವೇಗ ಗಂಟೆಗೆ {wind} ಕಿಲೋಮೀಟರ್ ವರೆಗೆ ಇರುತ್ತದೆ. "
    "ಮಳೆ ಬರುವ ಸಾಧ್ಯತೆ ಶೇಕಡಾ {rain} ಇದೆ. "
    "ಗಾಳಿಯಲ್ಲಿ ತೇವಾಂಶ ಶೇಕಡಾ {humidity} ಇರುತ್ತದೆ. "
    "ನಾನು ಪ್ರತಿ ಬೆಳಿಗ್ಗೆ ಹೀಗೆ ಹವಾಮಾನ ತಿಳಿಸಲು ಕರೆ ಮಾಡುತ್ತೇನೆ. "
    "ಈ ಕರೆಗಳು ಬೇಡವಾದರೆ, ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಗ್ರಿದಮ್ ಸಂಪರ್ಕ ವ್ಯಕ್ತಿಗೆ ತಿಳಿಸಿ. "
    "ಈ ಹವಾಮಾನ ಮಾಹಿತಿ ನಿಮಗೆ ಅರ್ಥವಾಯಿತೇ? ದಯವಿಟ್ಟು ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ."
)

_TE = (
    "నమస్కారం {name} గారు. నేను అగ్రిథమ్ నుండి వాతావరణ సమాచారం చెప్పడానికి ఫోన్ చేస్తున్నాను. "
    "ఈ రోజు {place} ప్రాంతం వాతావరణ సమాచారం ఇది. "
    "ఉష్ణోగ్రత {tmin} నుండి {tmax} డిగ్రీల మధ్య ఉంటుంది. "
    "గాలి వేగం గంటకు {wind} కిలోమీటర్ల వరకు ఉంటుంది. "
    "వర్షం పడే అవకాశం {rain} శాతం ఉంది. "
    "గాలిలో తేమ {humidity} శాతం ఉంటుంది. "
    "నేను ప్రతి ఉదయం ఇలాగే వాతావరణ సమాచారం చెప్పడానికి ఫోన్ చేస్తాను. "
    "ఈ ఫోన్లు మీకు వద్దనుకుంటే, దయచేసి మీ అగ్రిథమ్ సంప్రదింపు వ్యక్తికి చెప్పండి. "
    "ఈ వాతావరణ సమాచారం మీకు అర్థమైందా? దయచేసి అవును లేదా కాదు అని చెప్పండి."
)

_TEMPLATES = {Language.HI: _HI, Language.KN: _KN, Language.TE: _TE, Language.EN: _EN}


def build_message(farmer: FarmerContext, weather: WeatherReport) -> str:
    return _TEMPLATES[farmer.language].format(
        name=farmer.display_name, place=weather.place_name, tmin=weather.temp_min_c, tmax=weather.temp_max_c,
        wind=weather.wind_kmh, rain=weather.rain_chance_pct, humidity=weather.humidity_pct,
    )


def weather_variables(farmer: FarmerContext, weather: WeatherReport) -> dict[str, str]:
    """The per-farmer values the Sarvam agent speaks from. The names are the agent's declared variables
    (Sarvam rejects any name the agent does not declare), and every value is text."""
    return {
        "farmer_name": farmer.display_name, "place_name": weather.place_name,
        "temp_min_c": str(weather.temp_min_c), "temp_max_c": str(weather.temp_max_c),
        "wind_kmh": str(weather.wind_kmh), "rain_chance_pct": str(weather.rain_chance_pct),
        "humidity_pct": str(weather.humidity_pct),
    }


def estimate_seconds(text: str) -> float:
    return len(text.split()) / WORDS_PER_SECOND
