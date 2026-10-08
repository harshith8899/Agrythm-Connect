"""Conversation orchestrator — Gate 4 (conversation outcome) with Gate 3 enforced on every reply.

Turn-based for TRL 3 (text in, text out). STT/TTS wrap this at TRL 4 without changing it.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from .context import ContextPack, build_context
from .db import get_conversation, now
from .llm import LLMAdapter, RuleBasedAdapter, Understanding, render
from .models import TRANSITIONS, IllegalTransition, Outcome, State
from .policy import check_reply, mentioned_inputs

CONFIDENCE_THRESHOLD = 0.5


class PolicyBlocked(Exception):
    def __init__(self, violations: list[str]):
        super().__init__(", ".join(violations))
        self.violations = violations


def transition(conn: sqlite3.Connection, conversation_id: int, to_state: State, note: str = "") -> None:
    row = conn.execute("SELECT state FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    current = State(row["state"])
    if to_state not in TRANSITIONS[current]:
        raise IllegalTransition(f"{current.value} -> {to_state.value}")
    ts = now()
    with conn:
        conn.execute("UPDATE conversations SET state=?, updated_at=? WHERE id=?",
                     (to_state.value, ts, conversation_id))
        conn.execute(
            "INSERT INTO state_log(conversation_id,from_state,to_state,note,created_at) VALUES(?,?,?,?,?)",
            (conversation_id, current.value, to_state.value, note, ts))


class ConversationSession:
    def __init__(self, conn: sqlite3.Connection, conversation_id: int,
                 adapter: LLMAdapter | None = None, max_clarifications: int = 2,
                 language: str | None = None):
        self.conn = conn
        self.conversation_id = conversation_id
        self.adapter = adapter or RuleBasedAdapter()
        self.max_clarifications = max_clarifications
        self.ctx: ContextPack = build_context(conn, conversation_id)  # Gate 2: before any call
        if language is not None:  # per-call override of the farmer's stored preference
            if language not in ("hi", "en"):
                raise ValueError(f"unsupported language '{language}' (use 'hi' or 'en')")
            self.ctx.language = language
        self.clarifications = 0
        self.facts_used: list[str] = []
        self.policy_blocks: list[str] = []
        self.last_route: str | None = None
        self.closed = False

    # ------------------------------------------------------------------ public API
    def open(self) -> str:
        """Place the (simulated) call and speak the greeting + approved advisory."""
        transition(self.conn, self.conversation_id, State.CALLING, "dial (simulated)")
        transition(self.conn, self.conversation_id, State.CONNECTED, "farmer answered (simulated)")
        try:
            return self._say("greeting")
        except PolicyBlocked as blocked:
            return self._escalate(f"policy_gate_blocked_reply: {', '.join(blocked.violations)}", None)

    def respond(self, farmer_text: str) -> str:
        if self.closed:
            return self._static("closing_completed")
        try:
            return self._handle(farmer_text)
        except PolicyBlocked as blocked:
            self.policy_blocks.extend(blocked.violations)
            return self._escalate(f"policy_gate_blocked_reply: {', '.join(blocked.violations)}", None)

    def hang_up(self) -> None:
        """Farmer left without a clear commitment."""
        if self.closed:
            return
        state = self._state()
        if state == State.CLARIFICATION_REQUIRED:
            transition(self.conn, self.conversation_id, State.CONNECTED, "back to call")
        transition(self.conn, self.conversation_id, State.COMPLETED, "call ended without commitment")
        asked = ", ".join(self.facts_used) or "nothing"
        self._persist(Outcome.UNRESOLVED, "no_commitment", 0.0,
                      f"{self._who()}: call ended with no commitment captured (questions answered: {asked}).",
                      "retry_call")
        self.closed = True
        self.last_route = "unresolved"

    # ------------------------------------------------------------------ handling
    def _handle(self, text: str) -> str:
        u = self.adapter.understand(text, self.ctx)
        self._log_turn("farmer", text, u.intent, u.confidence)
        inputs = mentioned_inputs(text)
        if inputs:
            u.entities["mentioned_inputs"] = inputs

        if u.intent == "unclear" or u.confidence < CONFIDENCE_THRESHOLD:
            return self._clarify("ask_clarify", u)
        if u.intent == "not_understood":
            return self._clarify("re_explain", u)
        if u.intent == "question":
            if u.topic == "decision" or self.ctx.fact(u.topic) is None:
                return self._escalate(f"agronomic_question_outside_approved_context:{u.topic}", u)
            reply = self._say("answer", topic=u.topic)
            self.facts_used.append(u.topic)
            self.last_route = "answer"
            return reply
        if u.intent == "new_issue":
            return self._escalate(f"new_issue_reported:{u.entities.get('symptom', '')}", u)
        if u.intent == "reject":
            return self._escalate(f"advisory_rejected_by_farmer:{u.entities.get('barrier', 'unspecified')}", u)
        if u.intent == "delay":
            days = int(u.entities.get("delay_days", 2))
            return self._complete(Outcome.FOLLOW_UP_REQUIRED, u, f"reminder_call_in_{days}d",
                                  ("reminder", days), "follow_up", text,
                                  closing=self._static_text("closing_followup", days=days))
        if u.intent == "done":
            return self._complete(Outcome.COMPLETED, u, "none", None, "completed", text)
        if u.intent == "confirm":
            days = self.ctx.followup_days
            return self._complete(Outcome.COMPLETED, u, f"execution_check_in_{days}d",
                                  ("execution_check", days), "completed", text)
        return self._clarify("ask_clarify", u)

    def _clarify(self, kind: str, u: Understanding) -> str:
        self.clarifications += 1
        if self.clarifications > self.max_clarifications:
            return self._escalate("farmer_did_not_understand_after_clarification", u)
        transition(self.conn, self.conversation_id, State.CLARIFICATION_REQUIRED, u.intent)
        try:
            text = self._say(kind)
        except PolicyBlocked:
            raise
        transition(self.conn, self.conversation_id, State.CONNECTED, "clarification delivered")
        self.last_route = "clarify"
        return text

    def _escalate(self, reason: str, u: Understanding | None) -> str:
        transition(self.conn, self.conversation_id, State.HUMAN_ESCALATION, reason)
        transition(self.conn, self.conversation_id, State.AWAITING_HUMAN, "queued for SME")
        ts = now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO escalations(conversation_id,reason,recommended_handling,created_at) VALUES(?,?,?,?)",
                (self.conversation_id, reason,
                 "SME to call the farmer within 24h; review the transcript and approved context.", ts))
        self._persist(Outcome.HUMAN_ESCALATION, u.intent if u else "policy_block",
                      u.confidence if u else 0.0,
                      f"{self._who()}: escalated to a human ({reason}).",
                      "sme_callback_within_24h", reason, u.entities if u else {})
        self.closed = True
        self.last_route = "escalate"
        return self._static("closing_escalation")

    def _complete(self, outcome: Outcome, u: Understanding, next_action: str,
                  follow_up: tuple[str, int] | None, route: str, text: str,
                  closing: str | None = None) -> str:
        transition(self.conn, self.conversation_id, State.COMPLETED, outcome.value)
        if follow_up:
            kind, days = follow_up
            with self.conn:
                self.conn.execute(
                    "INSERT INTO follow_ups(conversation_id,farmer_id,crop_cycle_id,kind,due_date) VALUES(?,?,?,?,?)",
                    (self.conversation_id, self.ctx.farmer_id, self.ctx.crop_cycle_id, kind,
                     (date.today() + timedelta(days=days)).isoformat()))
        quote = text.strip()[:120]
        self._persist(outcome, u.intent, u.confidence,
                      f"{self._who()}: {u.intent}; outcome {outcome.value}. Farmer said: \"{quote}\"",
                      next_action, None, u.entities)
        self.closed = True
        self.last_route = route
        return self._static_log(closing or self._static_text("closing_completed"))

    # ------------------------------------------------------------------ helpers
    def _say(self, kind: str, **kw) -> str:
        text = self.adapter.compose(kind, self.ctx, **kw)
        result = check_reply(text, self.ctx.approved_corpus())
        if not result.allowed:
            raise PolicyBlocked(result.violations)
        self._log_turn("agent", text)
        return text

    def _static_text(self, kind: str, **kw) -> str:
        return render(kind, self.ctx, **kw)

    def _static(self, kind: str, **kw) -> str:
        return self._static_log(self._static_text(kind, **kw))

    def _static_log(self, text: str) -> str:
        self._log_turn("agent", text)
        return text

    def _log_turn(self, speaker: str, text: str, intent: str | None = None,
                  confidence: float | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO turns(conversation_id,speaker,text,intent,confidence,created_at) VALUES(?,?,?,?,?,?)",
                (self.conversation_id, speaker, text, intent, confidence, now()))

    def _state(self) -> State:
        return State(get_conversation(self.conn, self.conversation_id)["state"])

    def _who(self) -> str:
        return f"{self.ctx.farmer_name} ({self.ctx.crop}, {self.ctx.village})"

    def _persist(self, outcome: Outcome, intent: str, confidence: float, summary: str,
                 next_action: str, escalation_reason: str | None = None,
                 entities: dict | None = None) -> None:
        context_used = {
            "context": self.ctx.audit_dict(),
            "approved_facts_used": self.facts_used,
            "clarifications_asked": self.clarifications,
            "policy_blocks": self.policy_blocks,
            "adapter": self.adapter.name,
        }
        with self.conn:
            self.conn.execute(
                "UPDATE conversations SET outcome=?, intent=?, confidence=?, summary=?, next_action=?, "
                "escalation_reason=?, entities=?, context_used=?, updated_at=? WHERE id=?",
                (outcome.value, intent, confidence, summary, next_action, escalation_reason,
                 json.dumps(entities or {}, ensure_ascii=False),
                 json.dumps(context_used, ensure_ascii=False), now(), self.conversation_id))
