"""What the agent says first when a farmer rings the call-back line. The agent's default opening is the one for calls we place
("I am calling to give you weather information"), which is wrong when the farmer rings us, so each caller gets an opening that
fits what happened today. Sent with the roster as the cohort's initial_bot_message. The name is put in here, not left as a
placeholder. Hindi, Kannada and Telugu wording is a draft until a native speaker has reviewed it (rule 6 in CLAUDE.md)."""
from __future__ import annotations

# kind -> language -> text ({n} is the farmer's name with the respectful ending already attached)
_TEXT = {
    "ask": {
        "English": "Hello, welcome to Agrythm weather information. Am I speaking with {n}?",
        "Hindi": "नमस्ते, Agrythm मौसम जानकारी में आपका स्वागत है। क्या मेरी बात {n} से हो रही है?",
        "Kannada": "ನಮಸ್ಕಾರ, Agrythm ಹವಾಮಾನ ಮಾಹಿತಿಗೆ ಸ್ವಾಗತ. ನಾನು {n} ಜೊತೆ ಮಾತಾಡ್ತಿದ್ದೀನಾ?",
        "Telugu": "నమస్కారం, Agrythm వాతావరణ సమాచారానికి స్వాగతం. నేను {n}తోనే మాట్లాడుతున్నానా?",
    },
    "shared": {
        "English": "Hello {n}, we have already shared today's weather with you. The next update will come tomorrow. Thank you, have a good day from Agrythm.",
        "Hindi": "नमस्ते {n}, हमने आज का मौसम आपको पहले ही बता दिया है। अगली जानकारी कल मिलेगी। धन्यवाद, Agrythm की ओर से आपका दिन शुभ हो।",
        "Kannada": "ನಮಸ್ಕಾರ {n}, ಇಂದಿನ ಹವಾಮಾನವನ್ನು ನಾವು ನಿಮಗೆ ಈಗಾಗಲೇ ತಿಳಿಸಿದ್ದೇವೆ. ಮುಂದಿನ ಮಾಹಿತಿ ನಾಳೆ ಸಿಗುತ್ತದೆ. ಧನ್ಯವಾದಗಳು, Agrythm ಕಡೆಯಿಂದ ನಿಮ್ಮ ದಿನ ಶುಭವಾಗಿರಲಿ.",
        "Telugu": "నమస్కారం {n}, ఈ రోజు వాతావరణం గురించి మేము మీకు ఇప్పటికే చెప్పాము. తదుపరి సమాచారం రేపు వస్తుంది. ధన్యవాదాలు, Agrythm తరఫున మీ రోజు శుభంగా ఉండాలి.",
    },
    "declined": {
        "English": "Hello {n}, we noted that you do not need today's weather. The next update will come tomorrow. Thank you, have a good day from Agrythm.",
        "Hindi": "नमस्ते {n}, हमने नोट किया है कि आपको आज का मौसम नहीं चाहिए। अगली जानकारी कल मिलेगी। धन्यवाद, Agrythm की ओर से आपका दिन शुभ हो।",
        "Kannada": "ನಮಸ್ಕಾರ {n}, ನಿಮಗೆ ಇಂದಿನ ಹವಾಮಾನ ಬೇಡ ಎಂದು ನಾವು ಗಮನಿಸಿದ್ದೇವೆ. ಮುಂದಿನ ಮಾಹಿತಿ ನಾಳೆ ಸಿಗುತ್ತದೆ. ಧನ್ಯವಾದಗಳು, Agrythm ಕಡೆಯಿಂದ ನಿಮ್ಮ ದಿನ ಶುಭವಾಗಿರಲಿ.",
        "Telugu": "నమస్కారం {n}, మీకు ఈ రోజు వాతావరణం అవసరం లేదని మేము గమనించాము. తదుపరి సమాచారం రేపు వస్తుంది. ధన్యవాదాలు, Agrythm తరఫున మీ రోజు శుభంగా ఉండాలి.",
    },
    "stopped": {
        "English": "Hello {n}, as you asked, we have stopped the calls. Your Agrythm contact person can change that. Thank you, goodbye.",
        "Hindi": "नमस्ते {n}, आपके कहने पर हमने कॉल बंद कर दिए हैं। आपके Agrythm संपर्क व्यक्ति इसे बदल सकते हैं। धन्यवाद।",
        "Kannada": "ನಮಸ್ಕಾರ {n}, ನೀವು ಹೇಳಿದಂತೆ ನಾವು ಕರೆಗಳನ್ನು ನಿಲ್ಲಿಸಿದ್ದೇವೆ. ನಿಮ್ಮ Agrythm ಸಂಪರ್ಕ ವ್ಯಕ್ತಿ ಇದನ್ನು ಬದಲಾಯಿಸಬಹುದು. ಧನ್ಯವಾದಗಳು.",
        "Telugu": "నమస్కారం {n}, మీరు చెప్పినట్లు మేము కాల్స్ ఆపేశాము. మీ Agrythm సంప్రదింపు వ్యక్తి దీన్ని మార్చగలరు. ధన్యవాదాలు.",
    },
    "unknown": {
        "English": "Hello, this number is only for registered farmers. Please speak to your Agrythm contact person. Thank you, goodbye.",
        "Hindi": "नमस्ते, यह नंबर सिर्फ़ पंजीकृत किसानों के लिए है। कृपया अपने Agrythm संपर्क व्यक्ति से बात कीजिए। धन्यवाद।",
        "Kannada": "ನಮಸ್ಕಾರ, ಈ ಸಂಖ್ಯೆ ನೋಂದಾಯಿತ ರೈತರಿಗೆ ಮಾತ್ರ. ದಯವಿಟ್ಟು ನಿಮ್ಮ Agrythm ಸಂಪರ್ಕ ವ್ಯಕ್ತಿಯನ್ನು ಸಂಪರ್ಕಿಸಿ. ಧನ್ಯವಾದಗಳು.",
        "Telugu": "నమస్కారం, ఈ నంబర్ నమోదైన రైతులకు మాత్రమే. దయచేసి మీ Agrythm సంప్రదింపు వ్యక్తిని సంప్రదించండి. ధన్యవాదాలు.",
    },
}
_ENDING = {"Hindi": "{} जी", "Kannada": "{} ಅವರೇ", "Telugu": "{} గారు", "English": "{}"}                 # addressing someone
_ENDING_WITH = {"Hindi": "{} जी", "Kannada": "{} ಅವರ", "Telugu": "{} గారి", "English": "{}"}           # "speaking with {n}"
_KIND = {"completed": "shared", "declined": "declined", "stopped": "stopped", "unregistered": "unknown"}


def inbound_opening(state: str, language_name: str, name: str = "") -> str:
    """The first thing said to a caller in this state. state is a _caller_state value ('callback 14:15', 'missed', ... all
    mean 'ask who is speaking'); an unknown or unregistered number gets the registered-farmers-only sentence."""
    kind = _KIND.get(state.split(" ")[0], "ask")
    language = language_name if language_name in _ENDING else "English"
    if kind != "unknown" and not name.strip():
        kind = "unknown"                                   # no name to speak to: never greet someone as if they were known
    text = _TEXT[kind][language]
    ending = (_ENDING_WITH if kind == "ask" else _ENDING)[language]
    return text.replace("{n}", ending.format(name.strip()))
