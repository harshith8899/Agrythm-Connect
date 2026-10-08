"""Bare yes/no replies: a "no" means "not understood" after "Did you understand?"
and "will not do it" after "Will you follow this advice: yes or no?"."""
import pytest

from connect.db import get_conversation


def outcome(conn, s):
    return get_conversation(conn, s.conversation_id)


@pytest.mark.parametrize("text", ["yes", "y", "Yes.", "haan", "हाँ", "जी हाँ"])
def test_yes_completes(conn, make_session, text):
    s = make_session(5)
    s.respond(text)
    assert outcome(conn, s)["outcome"] == "Completed"


@pytest.mark.parametrize("text", ["no", "n", "nahi", "no thanks", "नहीं", "जी नहीं"])
def test_no_after_greeting_re_explains(conn, make_session, text):
    s = make_session(5)
    reply = s.respond(text)
    assert reply.startswith("No problem, let me say it again")
    assert not s.closed


def test_no_to_yes_no_question_escalates_as_rejection(conn, make_session):
    s = make_session(5)
    assert s.respond("hmm").endswith("yes or no?")
    s.respond("no")
    row = outcome(conn, s)
    assert row["outcome"] == "Human Escalation"
    assert row["escalation_reason"] == "advisory_rejected_by_farmer:unspecified"


def test_no_after_answered_question_escalates(conn, make_session):
    s = make_session(5)
    assert s.respond("why?").endswith("Will you be able to do this?")
    s.respond("no")
    assert outcome(conn, s)["outcome"] == "Human Escalation"


def test_repeated_no_after_greeting_escalates_after_two_clarifications(conn, make_session):
    s = make_session(5)
    s.respond("no")
    s.respond("no")
    assert not s.closed
    s.respond("no")
    row = outcome(conn, s)
    assert row["outcome"] == "Human Escalation"
    assert row["escalation_reason"] == "farmer_did_not_understand_after_clarification"


def test_no_then_yes_completes(conn, make_session):
    s = make_session(1, open_call=True)
    s.respond("nahi")
    s.respond("haan")
    assert outcome(conn, s)["outcome"] == "Completed"
