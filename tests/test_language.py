import json

import pytest

from connect.db import get_conversation
from connect.events import create_event
from connect.orchestrator import ConversationSession


def _session(conn, farmer_id, language=None):
    ev = create_event(conn, "advisory_approved", farmer_id, farmer_id, farmer_id)
    return ConversationSession(conn, ev.conversation_id, language=language)


def test_stored_language_is_default(conn):
    s = _session(conn, 1)
    assert s.ctx.language == "hi"
    assert "नमस्ते" in s.open()


def test_override_hindi_farmer_to_english(conn):
    s = _session(conn, 1, language="en")
    greeting = s.open()
    assert greeting.startswith("Hello Ramesh Yadav")
    assert "neem oil at 3 ml per litre" in greeting
    assert s.respond("how much to use?").startswith("As advised: neem oil, 3 ml per litre")
    assert s.respond("yes").startswith("Thank you, Ramesh Yadav")
    row = get_conversation(conn, s.conversation_id)
    assert row["outcome"] == "Completed"
    assert json.loads(row["context_used"])["context"]["language"] == "en"


def test_override_english_farmer_to_hindi(conn):
    s = _session(conn, 5, language="hi")
    assert "नमस्ते" in s.open()


def test_unsupported_language_rejected(conn):
    with pytest.raises(ValueError):
        _session(conn, 1, language="ta")


def test_cli_lang_flag(capsys, monkeypatch):
    from connect import cli
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(EOFError))
    assert cli.main(["--farmer", "1", "--lang", "en"]) == 0
    out = capsys.readouterr().out
    assert "Hello Ramesh Yadav" in out and '"outcome": "Unresolved"' in out
