"""Builds the spoken message. Pure function: weather + farmer in, text out. No provider calls.

The voice identifies as Chethan Sir's assistant from Agrythm Connect (AI assistant).
Available in English, Hindi, and Kannada.
"""
from __future__ import annotations

from .contracts import FarmerContext, Language, WeatherReport

WORDS_PER_SECOND = 2.4  # rough speaking pace; replaced by real measured length once TTS is connected

_SUMMARY_HI = {
    "clear sky": "साफ़ आकाश",
    "clear": "साफ़",
    "partly cloudy": "आंशिक रूप से बादल",
    "overcast": "घने बादल",
    "foggy": "कोहरा",
    "light rain": "हल्की बारिश",
    "heavy rain": "भारी बारिश",
    "freezing rain": "बर्फीली बारिश",
    "snow": "बर्फबारी",
    "rain showers": "बारिश की फुहारें",
    "snow showers": "हिमपात की फुहारें",
    "thunderstorms": "गरज के साथ बारिश",
}

_SUMMARY_KN = {
    "clear sky": "ಸ್ವಚ್ಛ ಆಕಾಶ",
    "clear": "ಸ್ವಚ್ಛ ವಾತಾವರಣ",
    "partly cloudy": "ಭಾಗಶಃ ಮೋಡ ಕವಿದ ವಾತಾವರಣ",
    "overcast": "ಮೋಡ ಕವಿದ ವಾತಾವರಣ",
    "foggy": "ಮಂಜು ಮುಸುಕಿದ ವಾತಾವರಣ",
    "light rain": "ಹಗುರ ಮಳೆ",
    "heavy rain": "ಭಾರಿ ಮಳೆ",
    "freezing rain": "ಹಿಮ ಮಳೆ",
    "snow": "ಹಿಮಪಾತ",
    "rain showers": "ಮಳೆಯ ತುಂತುರು",
    "snow showers": "ಹಿಮ ತುಂತುರು",
    "thunderstorms": "ಗುಡುಗು ಸಹಿತ ಮಳೆ",
}

_EN = (
    "Hello {greeting}, I am calling as Chethan Sir's assistant from Agrythm Connect. "
    "I am an AI voice assistant. "
    "Here is today's weather report for {place}. It will be {summary}. "
    "The temperature will be between {tmin} and {tmax} degrees Celsius. "
    "The wind speed is {wind} kilometers per hour. "
    "The rainfall probability is {rain} percent, and the humidity is {humidity} percent. "
    "Please plan your farm work for today with this in mind. "
    "I will call every morning like this with the weather. "
    "Thank you for listening. Have a good day."
)

_HI = (
    "नमस्ते {greeting}, मैं एग्रिदम कनेक्ट से चेतन सर के असिस्टेंट के रूप में बोल रही एआई आवाज़ हूँ। "
    "यह {place} का आज का मौसम है। आज मौसम {summary} रहेगा। "
    "तापमान {tmin} से {tmax} डिग्री सेल्सियस के बीच रहेगा। "
    "हवा की गति {wind} किलोमीटर प्रति घंटा रहेगी। "
    "बारिश की संभावना {rain} प्रतिशत है, और हवा में नमी {humidity} प्रतिशत रहेगी। "
    "कृपया आज के खेत के काम इसी हिसाब से तय करें। "
    "मैं हर सुबह इसी तरह मौसम की जानकारी देने के लिए फ़ोन करूँगी। "
    "सुनने के लिए धन्यवाद। आपका दिन शुभ हो।"
)

_KN = (
    "ನಮಸ್ಕಾರ {greeting}, ನಾನು ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್‌ನಿಂದ ಚೇತನ್ ಸರ್ ಅವರ ಅಸಿಸ್ಟೆಂಟ್ ಆಗಿ ಕರೆ ಮಾಡುತ್ತಿರುವ ಎಐ ಧ್ವನಿ ಸಹಾಯಕ. "
    "ಇದು {place} ನ ಇಂದಿನ ಹವಾಮಾನ ವರದಿ. ಇಂದು ಹವಾಮಾನ {summary} ಇರಲಿದೆ. "
    "ತಾಪಮಾನವು {tmin} ರಿಂದ {tmax} ಡಿಗ್ರಿ ಸೆಲ್ಸಿಯಸ್ ನಡುವೆ ಇರಲಿದೆ. "
    "ಗಾಳಿಯ ವೇಗ ಗಂಟೆಗೆ {wind} ಕಿಲೋಮೀಟರ್ ಇರಲಿದೆ. "
    "ಮಳೆಯ ಸಾಧ್ಯತೆ {rain} ಪ್ರತಿಶತ ಮತ್ತು ತೇವಾಂಶ {humidity} ಪ್ರತಿಶತ ಇರಲಿದೆ. "
    "ದಯವಿಟ್ಟು ಇಂದಿನ ಕೃಷಿ ಕೆಲಸಗಳನ್ನು ಇದಕ್ಕೆ ತಕ್ಕಂತೆ ಯೋಜಿಸಿ. "
    "ನಾನು ಪ್ರತಿದಿನ ಬೆಳಿಗ್ಗೆ ಹೀಗೆಯೇ ಹವಾಮಾನ ಮಾಹಿತಿ ನೀಡಲು ಕರೆ ಮಾಡುತ್ತೇನೆ. "
    "ನಿಮಗೆ ಈ ಕರೆಗಳು ಬೇಡವಾದಲ್ಲಿ, ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಗ್ರಿಥಮ್ ಸಂಪರ್ಕ ವ್ಯಕ್ತಿಗೆ ತಿಳಿಸಿ. "
    "ಕೇಳಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ದಿನ ಶುಭವಾಗಿರಲಿ."
)


def build_message(farmer: FarmerContext, weather: WeatherReport) -> str:
    name = farmer.display_name.strip() if farmer.display_name else ""
    if farmer.language is Language.KN:
        template = _KN
        summary = _SUMMARY_KN.get(weather.summary.lower(), weather.summary)
        greeting = f"{name} ಸರ್" if (name and name.lower() not in ("sir", "farmer", "ಸರ್", "ರೈತ")) else "ಸರ್"
    elif farmer.language is Language.HI:
        template = _HI
        summary = _SUMMARY_HI.get(weather.summary.lower(), weather.summary)
        greeting = f"{name} सर" if (name and name.lower() not in ("sir", "farmer", "सर", "किसान")) else "सर"
    else:
        template = _EN
        summary = weather.summary
        greeting = f"{name} Sir" if (name and name.lower() not in ("sir", "farmer")) else "Sir"

    wind_str = f"{weather.wind_speed_kmh:.1f}".rstrip("0").rstrip(".") if weather.wind_speed_kmh else "0"

    return template.format(
        greeting=greeting,
        place=weather.place_name,
        summary=summary,
        tmin=weather.temp_min_c,
        tmax=weather.temp_max_c,
        wind=wind_str,
        rain=weather.rain_chance_pct,
        humidity=weather.humidity_pct,
    )


def estimate_seconds(text: str) -> float:
    return len(text.split()) / WORDS_PER_SECOND
