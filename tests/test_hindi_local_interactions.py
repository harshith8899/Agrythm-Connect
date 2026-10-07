import json
# pyrefly: ignore [missing-import]
import pytest

from connect.db import get_conversation
from connect.models import Outcome


@pytest.mark.parametrize("farmer_utterance,expected_intent,expected_outcome", [
    # Respectful / colloquial acceptance
    ("हाँ भैया, कर देंगे", "confirm", "Completed"),
    ("जी साहब, हो जाएगा", "confirm", "Completed"),
    ("theek hai sahab, daal denge", "confirm", "Completed"),
    ("हाँ जी, समझ में आ गया, कर लेंगे", "confirm", "Completed"),
    ("निपटा देंगे", "confirm", "Completed"),

    # Already completed actions
    ("छिड़क दिया है", "done", "Completed"),
    ("nipta diya", "done", "Completed"),
    ("paani laga diya", "done", "Completed"),

    # Delay / scheduling
    ("अभी फुर्सत नहीं है", "delay", "Follow-up Required"),
    ("कल परसों में करेंगे", "delay", "Follow-up Required"),
    ("दो दिन बाद करेंगे", "delay", "Follow-up Required"),
    ("baad me dekhte hain", "delay", "Follow-up Required"),

    # Rejection / barriers
    ("हमसे ना होगा, पैसे की तंगी है", "reject", "Human Escalation"),
    ("बाजार में दवा नहीं मिल रही", "reject", "Human Escalation"),
    ("लेबर नहीं मिल रही", "reject", "Human Escalation"),

    # New issues / symptoms
    ("खेत में इल्ली लग गई है", "new_issue", "Human Escalation"),
    ("पत्ती मुड़ रही है और पीली पड़ रही है", "new_issue", "Human Escalation"),
    ("पौधे सूख रहे हैं", "new_issue", "Human Escalation"),

    # Unapproved decisions / dosage alterations
    ("दवाई तेज कर दें?", "question", "Human Escalation"),
    ("दवा बदल दें?", "question", "Human Escalation"),
    ("dugna daal dein?", "question", "Human Escalation"),
])
def test_local_hindi_farmer_utterances_and_outcomes(conn, make_session, farmer_utterance, expected_intent, expected_outcome):
    session = make_session(1)
    session.respond(farmer_utterance)
    row = get_conversation(conn, session.conversation_id)
    assert row["outcome"] == expected_outcome
    assert row["intent"] == expected_intent


def test_agent_replies_are_formal_and_respectful_hindi(conn, make_session):
    session = make_session(1, open_call=False)
    # 1. Greeting
    greeting = session.open()
    assert "नमस्ते Ramesh Yadav जी" in greeting
    assert "मैं Agrythm से बात कर रहा हूँ" in greeting
    assert "हमारे कृषि विशेषज्ञ ने आपके टमाटर का खेत देखा था" in greeting
    assert "क्या आप यह बात समझ गए?" in greeting

    # 2. Clarification (when unclear)
    clarification = session.respond("का बोले?")
    assert "माफ़ कीजिएगा" in clarification or "कोई बात नहीं" in clarification

    # 3. Answer to approved fact question
    answer = session.respond("कितनी दवाई लगेगी?")
    assert "नीम तेल" in answer
    assert "क्या आप इसे आसानी से कर पाएंगे?" in answer

    # 4. Closing completed
    closing = session.respond("हाँ भैया, निपटा देंगे")
    assert "बहुत धन्यवाद Ramesh Yadav जी" in closing
    assert "आपकी बात दर्ज कर ली गई है" in closing


def test_agent_escalation_reply_is_respectful(conn, make_session):
    session = make_session(1)
    escalation_reply = session.respond("इल्ली लग गई है")
    assert "कृषि विशेषज्ञ" in escalation_reply
    assert "जल्दी ही आपसे संपर्क करेंगे" in escalation_reply
    assert "बहुत धन्यवाद" in escalation_reply


def test_agent_followup_reply_is_respectful(conn, make_session):
    session = make_session(1)
    followup_reply = session.respond("कल परसों में करेंगे")
    assert "ठीक है Ramesh Yadav जी" in followup_reply
    assert "दिन बाद आपसे फिर संपर्क करेंगे" in followup_reply


