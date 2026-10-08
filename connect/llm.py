"""Understanding + reply adapter (provider-replaceable). See ADR 0001.

TRL 3 ships a deterministic, free, offline RuleBasedAdapter for English, Hindi (Devanagari)
and Hinglish (Roman Hindi). Free LLM tiers plug in behind the same `LLMAdapter` at TRL 4.
Anything an adapter composes is checked by the policy gate before the farmer hears it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from .context import ContextPack


@dataclass
class Understanding:
    intent: str  # confirm | done | delay | reject | new_issue | question | not_understood | unclear
    topic: str | None = None  # for questions: decision | phi | mixing | dose | timing | why | other
    confidence: float = 0.0
    entities: dict = field(default_factory=dict)


class LLMAdapter(Protocol):
    name: str

    def understand(self, utterance: str, ctx: ContextPack) -> Understanding: ...

    def compose(self, kind: str, ctx: ContextPack, **kw) -> str: ...


# --------------------------------------------------------------------------- templates
CROP_HI = {"tomato": "टमाटर", "chilli": "मिर्च", "onion": "प्याज़", "wheat": "गेहूं"}

TEMPLATES: dict[str, dict[str, str]] = {
    "greeting": {
        "hi": ("नमस्ते {name} जी, मैं Agrythm से बात कर रहा हूँ। बातचीत की गुणवत्ता और रिकॉर्ड के लिए यह कॉल "
               "दर्ज की जा सकती है। हमारे कृषि विशेषज्ञ ने आपके {crop} का खेत देखा था। उनकी "
               "सलाह यह है: {advisory} क्या आप यह बात समझ गए?"),
        "en": ("Hello {name}, this is a call from Agrythm. This conversation may be recorded for "
               "quality and records. Our expert recently visited your {crop} field. Their advice: "
               "{advisory} Did you understand?"),
    },
    "re_explain": {
        "hi": "कोई बात नहीं, मैं दोबारा बता देता हूँ: {advisory} क्या अब बात समझ में आ गई?",
        "en": "No problem, let me say it again: {advisory} Is that clear now?",
    },
    "ask_clarify": {
        "hi": "माफ़ कीजिएगा, मैं आपकी बात ठीक से समझ नहीं पाया। क्या आप यह सलाह अपना सकेंगे: हाँ या नहीं?",
        "en": "Sorry, I did not catch that. Will you follow this advice: yes or no?",
    },
    "answer": {
        "hi": "{fact} क्या आप इसे आसानी से कर पाएंगे?",
        "en": "{fact} Will you be able to do this?",
    },
    # Closing messages are fixed templates; they never pass through an adapter.
    "closing_completed": {
        "hi": "बहुत धन्यवाद {name} जी। आपकी बात दर्ज कर ली गई है।",
        "en": "Thank you, {name}. Your response has been recorded.",
    },
    "closing_followup": {
        "hi": "ठीक है {name} जी, हम {days} दिन बाद आपसे फिर संपर्क करेंगे। बहुत धन्यवाद।",
        "en": "Okay {name}, we will get back to you in {days} days.",
    },
    "closing_escalation": {
        "hi": "यह बात मैं हमारे कृषि विशेषज्ञ तक पहुँचा देता हूँ। वे जल्दी ही आपसे संपर्क करेंगे। बहुत धन्यवाद।",
        "en": "I am passing this to our agronomy expert. They will contact you soon. Thank you.",
    },
    "closing_unresolved": {
        "hi": "आपसे बातचीत पूरी नहीं हो पाई। हम आपसे फिर से संपर्क करेंगे। बहुत धन्यवाद।",
        "en": "We could not finish our conversation. We will contact you again. Thank you.",
    },
}



def render(kind: str, ctx: ContextPack, **kw) -> str:
    crop = CROP_HI.get(ctx.crop, ctx.crop) if ctx.language == "hi" else ctx.crop
    fields = dict(name=ctx.farmer_name, crop=crop, advisory=ctx.advisory_text, **kw)
    if "topic" in kw and "fact" not in kw:
        fields["fact"] = ctx.fact(kw["topic"]) or ""
    return TEMPLATES[kind][ctx.language].format(**fields)


# --------------------------------------------------------------------------- understanding
def _canon(text: str) -> str:
    t = text.lower().replace("'", "").replace("’", "").replace("ँ", "ं")
    t = t.replace("no problem", "ok").replace("not a problem", "ok")
    t = re.sub(r"[^\wऀ-ॿ\s%]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    padded = f" {t} "
    for a, b in (
        (" नही ", " नहीं "), (" नहि ", " नहीं "), (" करुंगा ", " करूंगा "),
        (" करुंगी ", " करूंगी "), (" nahin ", " nahi "), (" nai ", " nahi "),
        (" gya ", " gaya "), (" gye ", " gaye "), (" gyi ", " gayi "),
        (" gae ", " gaye "), (" gai ", " gayi "),
        (" bhaya ", " bhaiya "), (" bhaii ", " bhaiya "),
        (" saheb ", " sahab "), (" sahib ", " sahab "),
        (" theek ", " thik "),
    ):
        padded = padded.replace(a, b)
    return padded.strip()


def _has(c: str, phrases: list[str]) -> str | None:
    padded = f" {c} "
    for p in phrases:
        if f" {p} " in padded:
            return p
    return None


NOT_UNDERSTOOD = [
    # Hinglish & colloquial phrases
    "samajh nahi", "samjha nahi", "samjh nahi", "samajh nahi aaya", "samajh me nahi",
    "samajh nahi paya", "samajh nahi pada", "samajh nahi baitha", "pata nahi chala",
    "phir se", "dobara", "dubara", "repeat", "again", "kya bola", "kya kaha",
    "ka bole", "ka kahe", "ka bol rahe", "kya bole", "sunai nahi diya", "aawaz nahi",
    "aawaz kat rahi", "phir se bolo", "phir se batao", "phir se kahiye", "ek baar aur",
    "jara dobara", "jara fir se", "kuch palle nahi", "kuch nahi samjhe", "didnt understand",
    "did not understand", "dont understand", "do not understand", "not clear",
    "cant understand", "cant follow", "pardon", "slowly",
    # Devanagari
    "समझ नहीं", "समझा नहीं", "समझ में नहीं", "समझ नहीं आया", "समझ नहीं पड़ा",
    "फिर से", "दोबारा", "दुबारा", "क्या बोला", "क्या कहा", "का बोले", "का कहे",
    "क्या बोले", "सुनाई नहीं दिया", "आवाज नहीं", "आवाज़ नहीं", "आवाज कट रही",
    "फिर से बोलिए", "फिर से बताइए", "फिर से कहिए", "एक बार और", "जरा दोबारा",
    "पल्ले नहीं पड़ा", "कुछ नहीं समझे", "कुछ समझ नहीं",
]
NEW_ISSUE = [
    # Hinglish
    "naya problem", "new problem", "problem", "dikkat", "samasya", "keede", "keeda",
    "kide", "kida", "illi", "sundi", "sundee", "lata", "lat", "mudiya", "marod",
    "jhulsa", "sadan", "galan", "fungus", "chikna", "dhabba", "phaphoondi",
    "safed makkhi", "chepa", "tela", "tele", "moila", "mahun", "peele", "peeli",
    "pili", "pila", "yellow", "yellowing", "sookh", "sukh", "sookhne", "sookh raha",
    "wilt", "wilting", "murjha", "murjhaa", "daag", "dhabbe", "spots", "bimari",
    "disease", "pest", "pests", "insects", "rog", "kharab ho raha", "kharab ho rahi",
    "gir rahe", "jhad rahe", "kat rahe",
    # Devanagari
    "कीड़े", "कीड़ा", "इल्ली", "सुंडी", "लट", "झुलसा", "सड़न", "गलन", "फफूंद",
    "फफूंदी", "सफेद मक्खी", "चेपा", "तेला", "तेले", "मोयला", "माहूं", "मरोड़िया",
    "मुड़ रहे", "पीली", "पीले", "पीला", "सूख", "सूख रहा", "समस्या", "बीमारी",
    "दाग", "धब्बे", "मुरझा", "रोग", "दिक्कत", "खराब हो रहा", "खराब हो रही",
    "झड़ रहे", "गिर रहे", "कट रहे",
]
TOPIC_KEYWORDS: list[tuple[str, list[str]]] = [
    ("decision", [
        # Hinglish
        "double", "dugna", "dugni", "duguna", "zyada", "jyada", "badha", "badhao",
        "badha de", "badha du", "tez kar", "tez ghol", "alag dawa", "dusri dawa",
        "doosri dawa", "koi aur dawa", "koi doosri dawa", "kaunsi dawa", "konsi dawa",
        "which spray", "which pesticide", "which medicine", "what should i spray",
        "what to spray", "instead", "replace", "badal", "badle", "badal de", "badal du",
        "switch", "daal du", "dal du", "daal dun", "daalun", "dalun", "daal doon",
        "chhidak du", "chhidak de", "chhidkun", "aur daal de",
        # Devanagari
        "दुगना", "दुगुना", "ज्यादा", "बढ़ा", "बढ़ा दें", "बढ़ा दूं", "तेज कर दें",
        "दूसरी दवा", "कोई और दवा", "कोई दूसरी दवा", "कौन सी दवा", "कौनसी दवा",
        "बदल", "बदल दें", "बदल दूं", "डाल दूं", "डाल दें", "छिड़क दूं", "छिड़क दें",
    ]),
    ("phi", [
        # Hinglish
        "harvest", "harvesting", "tod", "todne", "tudai", "tudaai", "waiting period",
        "phi", "khudai", "nikasi", "kab tode", "kab kaate", "kab khode", "todna kab",
        # Devanagari
        "कटाई", "तोड़", "तोड़ने", "तुड़ाई", "खुदाई", "निकासी", "कब तोड़ें", "कब काटें",
        "कब खोदें", "तोड़ना कब", "तुड़ाई कब",
    ]),
    ("mixing", [
        # Hinglish
        "mila", "milake", "milana", "mila ke", "mila lein", "mila len", "mila sakte",
        "mila sakti", "ghol lein", "ghol ke", "dono saath", "ek saath", "mix",
        "mixing", "together", "compatible",
        # Devanagari
        "मिला", "मिलाकर", "मिलाना", "मिला के", "मिला लें", "मिला सकते", "मिला सकती",
        "घोल लें", "घोल के", "दोनों साथ", "एक साथ",
    ]),
    ("dose", [
        # Hinglish
        "kitna", "kitni", "dose", "dosage", "quantity", "matra", "ml", "litre",
        "liter", "gram", "how much", "kitna padega", "kitna lagega", "kitni lagegi",
        "kitna dalna", "kitna chhidakna", "kitna gholna", "kitna milana", "tanki me kitna",
        "naap kya", "kitni dawai", "kitna ghol",
        # Devanagari
        "कितना", "कितनी", "मात्रा", "डोज", "कितना पड़ेगा", "कितना लगेगा", "कितनी लगेगी",
        "कितना डालना", "कितना छिड़कना", "कितना घोलना", "कितना मिलाना", "टंकी में कितना",
        "नाप क्या", "कितनी दवाई",
    ]),
    ("timing", [
        # Hinglish
        "kab", "when", "samay", "kitne din", "kis din", "what time", "kis samay",
        "kaun samay", "kone samay", "kaun se time", "subah ki shaam", "subah ya shaam",
        "shaam ya subah", "shaam ko", "sham ko", "subah ko", "subah", "shaam", "sham",
        "kab chhidke", "kab chhidkna", "kab dale", "kab dalna", "kis vakt", "kis waqt",
        # Devanagari
        "कब", "समय", "कितने दिन", "किस दिन", "किस समय", "कौने समय", "सुबह या शाम",
        "शाम या सुबह", "सुबह की शाम", "शाम को", "सुबह को", "सुबह", "शाम",
        "कब छिड़कें", "कब छिड़कना", "कब डालें", "कब डालना", "किस वक्त",
    ]),
    ("why", [
        # Hinglish
        "kyun", "kyon", "kyu", "why", "kis liye", "kisliye", "kahe", "kahe karna",
        "kis wajah se", "kis kaaran", "isse kya hoga", "kya fayda", "ka fayda",
        "kya laabh", "kya labh",
        # Devanagari
        "क्यों", "क्यूं", "क्यु", "काहे", "काहे करना", "किस वजह से", "किस कारण",
        "इससे क्या होगा", "क्या फायदा", "का फायदा", "क्या लाभ",
    ]),
]
Q_WORDS = [
    # Hinglish
    "kya", "kitna", "kitni", "kitne", "kab", "kaise", "kyun", "kyon", "kyu", "kaun",
    "kaunsi", "konsi", "kahe", "ka", "kone", "kauna", "how", "when", "why", "which",
    "what", "can", "should", "ya",
    # Devanagari
    "क्या", "कितना", "कितनी", "कितने", "कब", "कैसे", "क्यों", "क्यूं", "कौन",
    "काहे", "का", "कौने", "कौना", "या",
]
REJECT = [
    # Hinglish
    "nahi karunga", "nahi karungi", "nahi kar sakta", "nahi kar sakti", "nahi kar paunga",
    "nahi kar paungi", "nahi kar sakte", "nahi karenge", "nahi karna", "nahi chahiye",
    "mana", "wont", "cant", "cannot", "afford", "paisa nahi", "paise nahi", "humse na hoga",
    "humse nahi ho payega", "na ho payega", "paise ki dikkat", "paise ki tangi",
    "itna kharcha nahi", "paisa nahi hai", "bajat nahi", "budget nahi", "bajaar me nahi",
    "dukan pe nahi", "mil nahi raha", "mil nahi rahi", "nahi mil raha", "nahi mil rahi",
    "nahi milta", "nahi milti", "majdoor nahi", "labour nahi",
    # Devanagari
    "नहीं करूंगा", "नहीं करूंगी", "नहीं कर सकता", "नहीं कर सकती", "नहीं कर पाऊंगा",
    "नहीं कर पाऊंगी", "नहीं कर सकते", "नहीं करेंगे", "नहीं करना", "नहीं चाहिए",
    "पैसे नहीं", "पैसा नहीं", "मना", "हमसे ना होगा", "हमसे नहीं हो पाएगा", "ना हो पाएगा",
    "पैसे की दिक्कत", "पैसे की तंगी", "इतना खर्चा नहीं", "पैसा नहीं है", "बजट नहीं है",
    "बाजार में नहीं", "दुकान पे नहीं", "मिल नहीं रहा", "मिल नहीं रही", "नहीं मिल रहा",
    "नहीं मिल रही", "नहीं मिलता", "नहीं मिलती", "मजदूर नहीं", "लेबर नहीं",
]
BARE_NO = {"nahi", "no", "na", "nope", "n", "no thanks", "no sir", "nahi ji", "ji nahi",
           "नहीं", "ना", "नहीं जी", "जी नहीं"}
DELAY = [
    # Hinglish
    "kal", "baad mein", "baad me", "later", "tomorrow", "parso", "agle hafte", "next week",
    "thodi der", "abhi nahi", "not now", "time nahi", "vyast", "busy", "abhi fursat nahi",
    "fursat nahi hai", "abhi time nahi", "kal parso", "do din baad", "char din baad",
    "baad me dekhte", "baad me karenge", "ruk ke karenge", "thoda ruk ke",
    "abhi kaam chal raha", "kaam me lage",
    # Devanagari
    "कल", "बाद में", "परसों", "अगले हफ्ते", "अभी नहीं", "व्यस्त", "अभी फुर्सत नहीं",
    "फुर्सत नहीं है", "अभी समय नहीं", "कल परसों", "दो दिन बाद", "चार दिन बाद",
    "बाद में देखते हैं", "बाद में करेंगे", "रुक के करेंगे", "थोड़ा रुक के",
    "अभी काम में लगे हैं",
]
DONE = [
    # Hinglish
    "kar diya", "ho gaya", "kar chuka", "kar chuki", "kar liya", "kar di", "already",
    "done", "did it", "completed", "finished", "kar diya hai", "nipta diya",
    "chhidak diya", "chhidkaav ho gaya", "paani laga diya", "daal diya", "ho gaya hai",
    "pehle hi kar diya", "kar diye", "kar diye hain",
    # Devanagari
    "कर दिया", "हो गया", "कर चुका", "कर चुकी", "कर लिया", "कर दिया है", "निपटा दिया",
    "छिड़क दिया", "छिड़काव हो गया", "पानी लगा दिया", "डाल दिया", "हो गया है",
    "पहले ही कर दिया", "कर दिए हैं", "कर दिए",
]
CONFIRM = [
    # Hinglish
    "haan", "han", "ha", "haa", "ji", "ji haan", "theek hai", "thik hai", "theek",
    "samajh gaya", "samajh gayi", "samjha", "samajh aa gaya", "samajh me aa gaya",
    "samajh gye", "samajh gaye", "ok", "okay", "yes", "y", "yep", "yeah", "sure", "kar dunga",
    "karunga", "karungi", "kar lunga", "kar lungi", "kar denge", "kar lenge", "will do",
    "i will", "alright", "bilkul", "haan bhaiya", "ji bhaiya", "ji saheb", "ji sahab",
    "theek hai saheb", "theek hai sahab", "ho jayega", "chhidak denge", "daal denge",
    "haan ji", "haan sahab", "bilkul kar denge", "nipta denge",
    # Devanagari
    "हां", "हाँ", "जी", "जी हाँ", "जी हां", "ठीक है", "ठीक", "समझ गया", "समझ गई",
    "समझ आ गया", "समझ में आ गया", "समझ गए", "कर दूंगा", "करूंगा", "करूंगी",
    "कर लूंगा", "कर देंगे", "कर लेंगे", "बिलकुल", "बिल्कुल", "हाँ भैया", "जी भैया",
    "जी साहब", "ठीक है साहब", "हो जाएगा", "छिड़क देंगे", "डाल देंगे", "हाँ जी",
    "हाँ साहब", "बिल्कुल कर देंगे", "निपटा देंगे",
]


def _delay_days(c: str) -> int:
    if _has(c, ["agle hafte", "next week", "अगले हफ्ते", "hafta", "hafte", "हफ्ते"]):
        return 7
    if _has(c, ["parso", "परसों", "do din", "दो दिन", "char din", "चार दिन"]):
        return 2
    if _has(c, ["kal", "tomorrow", "कल"]):
        return 1
    return 2


def _barrier(c: str) -> str:
    if _has(c, ["paisa", "paise", "पैसा", "पैसे", "afford", "cost", "mehnga", "महंगा",
                "tangi", "तंगी", "kharcha", "खर्चा", "budget", "bajat", "बजट"]):
        return "cost"
    if _has(c, ["time", "samay", "busy", "vyast", "व्यस्त", "समय", "fursat", "phursat", "फुर्सत", "kaam", "काम"]):
        return "time"
    if _has(c, ["labour", "labor", "majdoor", "मजदूर", "लेबर", "kamdar", "कामदार"]):
        return "labour"
    if _has(c, ["available", "uplabdh", "उपलब्ध", "milta", "मिलता", "mil raha", "mil rahi", "मिल रहा", "मिल रही", "dukan", "दुकान", "bajaar", "bazar", "बाजार"]):
        return "input_unavailable"
    return "unspecified"


def _topic(c: str) -> str | None:
    for topic, words in TOPIC_KEYWORDS:
        if _has(c, words):
            return topic
    return None


class RuleBasedAdapter:
    name = "rule-based"

    def understand(self, utterance: str, ctx: ContextPack) -> Understanding:
        c = _canon(utterance)
        if not c:
            return Understanding("unclear", None, 0.2)
        if _has(c, NOT_UNDERSTOOD):
            return Understanding("not_understood", None, 0.9)
        sym = _has(c, NEW_ISSUE)
        if sym:
            return Understanding("new_issue", None, 0.85, {"symptom": sym})

        topic = _topic(c)
        is_q = bool(_has(c, Q_WORDS)) or ("?" in utterance and topic is not None)
        # Safety bias: anything touching decisions, harvest intervals or mixing is a question.
        if topic in ("decision", "phi", "mixing") or is_q:
            if topic:
                return Understanding("question", topic, 0.85, {"topic": topic})
            return Understanding("question", "other", 0.7, {"topic": "other"})

        if c in BARE_NO:
            # Meaning depends on the question just asked; the orchestrator resolves it.
            return Understanding("reject", None, 0.45, {"barrier": "unspecified", "bare_no": True})
        if _has(c, REJECT):
            return Understanding("reject", None, 0.9, {"barrier": _barrier(c)})
        if _has(c, DELAY):
            return Understanding("delay", None, 0.9, {"delay_days": _delay_days(c)})
        if _has(c, DONE):
            return Understanding("done", None, 0.9, {"action_status": "done"})
        if _has(c, CONFIRM):
            return Understanding("confirm", None, 0.88, {"action_status": "acknowledged"})
        return Understanding("unclear", None, 0.2)

    def compose(self, kind: str, ctx: ContextPack, **kw) -> str:
        return render(kind, ctx, **kw)

