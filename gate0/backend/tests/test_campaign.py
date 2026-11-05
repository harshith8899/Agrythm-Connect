import io
import json
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime

import pytest

from weathercall.adapters.local import InMemoryFarmerSource, SQLiteLedger
from weathercall.adapters.mock import MockTelephony, MockVoice, MockWeather
from weathercall.adapters.sarvam_campaign import IST, CampaignStore, SarvamCampaigns
from weathercall.campaign import push, sync
from weathercall.config import Settings
from weathercall.contracts import FarmerContext, FinalResult, Language, SkipReason
from weathercall.engine import Ports
from weathercall.schedule import task_xml

D = date(2026, 10, 27)
ENV = {"SARVAM_AGENT_API_KEY": "sk-agent", "SARVAM_ORG_ID": "org1", "SARVAM_WORKSPACE_ID": "ws1",
       "SARVAM_APP_ID": "app1", "SARVAM_CONNECTION_ID": "conn1", "SARVAM_AGENT_PHONE": "+918000000000"}


def farmer(i, place="Mandya", consent=True, lang=Language.HI):
    return FarmerContext(f"F{i}", f"Name{i}", lang, place, 12.5, 76.9, consent, True, f"98765432{i:02d}")


class FakeSarvam:
    def __init__(self, attempts=None, transcripts=None):
        self.requests, self.attempt_items, self.transcripts = [], attempts or [], transcripts or {}

    def __call__(self, req, timeout):
        self.requests.append(req)
        path = urllib.parse.urlparse(req.full_url).path
        if "/transcripts/" in path:
            iid = urllib.parse.unquote(path.split("/transcripts/", 1)[1])
            if self.transcripts.get(iid) == "boom":
                raise urllib.error.HTTPError(req.full_url, 500, "err", {}, io.BytesIO(b"{}"))
            return io.BytesIO(json.dumps({"interaction_id": iid, "messages": self.transcripts.get(iid, [])}).encode())
        if path.endswith("/campaigns"):
            return io.BytesIO(json.dumps({"campaign_id": "camp-1", "status": "scheduled"}).encode())
        if path.endswith("/cohorts/stream"):
            return io.BytesIO(json.dumps({"cohort_id": "coh-1", "status": "processing"}).encode())
        return io.BytesIO(json.dumps({"items": self.attempt_items, "next_page_uri": ""}).encode())

    def bodies(self, suffix):
        return [json.loads(r.data) for r in self.requests if urllib.parse.urlparse(r.full_url).path.endswith(suffix)]


def setup(farmers, attempts=None, transcripts=None):
    http = FakeSarvam(attempts, transcripts)
    api = SarvamCampaigns(env=ENV, opener=http)
    store = CampaignStore()
    store.save_campaign("camp-1", D, 4, "09:00", "11:00")
    ports = Ports(InMemoryFarmerSource(farmers), SQLiteLedger(), MockWeather(), MockVoice(), MockTelephony())
    return ports, store, api, http


def test_create_campaign_window_retries_and_timezone():
    http = FakeSarvam()
    cid = SarvamCampaigns(env=ENV, opener=http).create_campaign("Gate0", D, 4, "09:00", "11:00", 3, 30)
    body = http.bodies("/campaigns")[0]
    assert cid == "camp-1"
    assert body["start_timestamp"] == "2026-10-27T09:00:00+05:30" and body["end_timestamp"] == "2026-10-30T11:00:00+05:30"
    assert body["allowed_schedule"]["allowed_start_time"] == "09:00" and body["allowed_schedule"]["timezone"] == "Asia/Kolkata"
    assert len(body["allowed_schedule"]["allowed_days"]) == 7
    rc = body["app_config"]["retry_config"]
    assert rc["max_retries"] == 2 and rc["retry_interval_minutes"] == 30 and rc["retry_on"]["no_answer"]["enabled"]
    assert body["app_config"]["connection_configs"][0]["phone_numbers"] == ["+918000000000"]


def test_push_sends_only_eligible_farmers_with_their_message_once():
    ports, store, api, http = setup([farmer(1), farmer(2, lang=Language.EN, place="Mysuru"),
                                     farmer(3, consent=False), farmer(4, place="Nowhere")])
    out = push(D, ports, Settings(), store, api, now=datetime(2026, 10, 27, 8, 30, tzinfo=IST))
    users = http.bodies("/cohorts/stream")[0]["users"]
    assert [u["user_identifier"] for u in users] == ["F1", "F2"]
    assert users[0]["user_phone_number"] == "+919876543201"
    # the agent greets and gives the weather itself, from these per-farmer variables (names must match the agent's)
    assert users[0]["app_overrides"] == {"initial_language_name": "Hindi"}
    assert users[1]["app_overrides"] == {"initial_language_name": "English"}
    assert users[0]["app_variables"] == {"farmer_name": "Name1", "place_name": "Mandya", "temp_min_c": "21",
                                         "temp_max_c": "32", "wind_kmh": "14", "rain_chance_pct": "20",
                                         "humidity_pct": "62", "now_text": "Tuesday, 27 October 2026, 08:30 AM"}
    assert users[1]["app_variables"]["place_name"] == "Mysuru" and users[1]["app_variables"]["humidity_pct"] == "48"
    assert "98765432" not in json.dumps([u["app_variables"] for u in users])        # no phone number inside variables
    rows = {r.farmer_id: r for r in ports.ledger.status(D).rows}
    assert rows["F3"].skip_reason is SkipReason.NO_CONSENT and rows["F4"].skip_reason is SkipReason.NO_WEATHER
    assert "pushed 2" in out[0]
    push(D, ports, Settings(), store, api)                    # a second run the same day pushes nobody
    assert len(http.bodies("/cohorts/stream")) == 1
    assert "98765432" not in repr(store.db.execute("SELECT * FROM sarvam_queue").fetchall())


def test_push_without_campaign_does_nothing():
    ports, _, api, http = setup([farmer(1)])
    out = push(D, ports, Settings(), CampaignStore(), api)
    assert "no Sarvam campaign" in out[0] and http.requests == []


def attempt(fid, status, n, nxt="UNKNOWN", dur=0):
    return {"attempt_id": f"a-{fid}-{n}", "user_identifier": fid, "connectivity_status": status, "retry_attempt": n,
            "next_action_status": nxt, "duration_in_seconds": dur, "failure_reason": "NO_FAILURE_REASON",
            "user_contact": "+919999999999"}


def test_sync_records_final_results_and_leaves_retries_pending():
    farmers = [farmer(1), farmer(2), farmer(3), farmer(4)]
    items = [attempt("F1", "no_answer", 1, "retry"), attempt("F1", "connected", 2, dur=38),
             attempt("F2", "no_answer", 1, "retry"), attempt("F2", "busy", 2, "retry"), attempt("F2", "no_answer", 3),
             attempt("F3", "no_answer", 1, "retry")]
    ports, store, api, _ = setup(farmers, items)
    push(D, ports, Settings(), store, api)
    during = datetime(2026, 10, 27, 10, 0, tzinfo=IST)
    out = sync(D, ports, store, api, now=during)
    rows = {r.farmer_id: r for r in ports.ledger.status(D).rows}
    assert (rows["F1"].result, rows["F1"].attempts) == (FinalResult.ANSWERED, 2)
    assert (rows["F2"].result, rows["F2"].attempts) == (FinalResult.UNANSWERED, 3)
    assert "F3" not in rows and "F4" not in rows and "still in progress 2" in out[0]
    dur = ports.ledger.db.execute("SELECT duration_s, provider_call_id FROM attempts WHERE farmer_id='F1' AND attempt_no=2")
    assert dur.fetchone() == (38, "a-F1-2")
    after = datetime(2026, 10, 27, 13, 0, tzinfo=IST)
    sync(D, ports, store, api, now=after)                    # F4 was never dialled in the window -> failed
    rows = {r.farmer_id: r for r in ports.ledger.status(D).rows}
    assert rows["F4"].result is FinalResult.FAILED and "F3" not in rows
    assert ports.ledger.db.execute("SELECT COUNT(*) FROM attempts WHERE farmer_id='F1'").fetchone()[0] == 2


AFTER = datetime(2026, 10, 27, 13, 0, tzinfo=IST)


def detail_attempt(fid, status, n, iid=None, ended="NO_END_REASON", reason="NO_FAILURE_REASON", summary=None):
    a = attempt(fid, status, n)
    a.update({"interaction_id": iid, "ended_by": ended, "failure_reason": reason,
              "agent_variables": {"call_summary": summary, "weather_message": "Hello Name1"} if summary else None})
    return a


def details(store):
    rows = store.db.execute("SELECT farmer_id, call_date, attempt_id, interaction_id, ended_by, failure_reason, "
                            "summary, transcript, fetched_at FROM call_details ORDER BY farmer_id, attempt_id")
    return [dict(zip(("farmer_id", "call_date", "attempt_id", "interaction_id", "ended_by", "failure_reason",
                      "summary", "transcript", "fetched_at"), r)) for r in rows]


def test_sync_saves_call_details_with_transcript_and_summary():
    turns = [{"turn_id": 1, "role": "assistant", "content": "Namaste, main AI hoon. Aaj Mandya mein badal.",
              "language_name": "Hindi"},
             {"turn_id": 2, "role": "user", "content": "Theek hai, dhanyavaad", "language_name": "Hindi"}]
    items = [detail_attempt("F1", "no_answer", 1, reason="exotel: callee did not pick up within 45 seconds"),
             detail_attempt("F1", "connected", 2, iid="20261027/abc-1", ended="AGENT_ENDS",
                            summary="Farmer heard the weather and thanked the agent."),
             detail_attempt("F2", "failed", 1, reason="vobiz: number unreachable after network timeout")]
    ports, store, api, http = setup([farmer(1), farmer(2)], items, {"20261027/abc-1": turns})
    push(D, ports, Settings(), store, api)
    out = sync(D, ports, store, api, now=AFTER)
    rows = details(store)
    assert [(r["farmer_id"], r["attempt_id"]) for r in rows] == [("F1", "a-F1-1"), ("F1", "a-F1-2"), ("F2", "a-F2-1")]
    no_answer, answered, failed = rows
    assert no_answer["failure_reason"] == "exotel: callee did not pick up within 45 seconds"   # full, not cut
    assert no_answer["transcript"] is None and no_answer["interaction_id"] is None
    assert answered["interaction_id"] == "20261027/abc-1" and answered["ended_by"] == "AGENT_ENDS"
    assert answered["summary"] == "Farmer heard the weather and thanked the agent."
    assert [t["role"] for t in json.loads(answered["transcript"])] == ["assistant", "user"]
    assert answered["call_date"] == "2026-10-27" and answered["fetched_at"]
    assert failed["failure_reason"] == "vobiz: number unreachable after network timeout"
    assert any("/transcripts/20261027" in r.full_url for r in http.requests)
    assert "details 3" in out[0]


def test_call_details_never_hold_phone_numbers():
    turns = [{"turn_id": 1, "role": "user", "content": "call me on 98765 43210 or +91-9123456789",
              "language_name": "English"}]
    items = [detail_attempt("F1", "connected", 1, iid="20261027/abc-2", ended="USER_ENDS",
                            summary="Farmer asked for a callback on 9876543210",
                            reason="NO_FAILURE_REASON"),
             detail_attempt("F2", "failed", 1, reason="provider rejected +919876543202 as invalid")]
    ports, store, api, _ = setup([farmer(1), farmer(2)], items, {"20261027/abc-2": turns})
    push(D, ports, Settings(), store, api)
    lines = sync(D, ports, store, api, now=AFTER)
    stored = repr(store.db.execute("SELECT * FROM call_details").fetchall())
    for digits in ("9876543210", "9123456789", "9876543202", "+919999999999", "98765 43210"):
        assert digits not in stored and digits not in "\n".join(lines)
    assert "[number removed]" in stored


def test_transcript_failure_keeps_the_rest_and_sync_is_idempotent():
    items = [detail_attempt("F1", "connected", 1, iid="20261027/bad", ended="USER_ENDS", summary="ok"),
             detail_attempt("F2", "connected", 1, iid="20261027/good", ended="AGENT_ENDS")]
    ports, store, api, http = setup([farmer(1), farmer(2)], items,
                                    {"20261027/bad": "boom", "20261027/good": [{"turn_id": 1, "role": "assistant",
                                                                              "content": "hi", "language_name": "English"}]})
    push(D, ports, Settings(), store, api)
    out = sync(D, ports, store, api, now=AFTER)
    rows = {r["farmer_id"]: r for r in details(store)}
    assert rows["F1"]["transcript"] is None and rows["F1"]["summary"] == "ok"
    assert json.loads(rows["F2"]["transcript"])[0]["content"] == "hi" and rows["F2"]["summary"] is None
    assert "transcript errors 1" in out[0]
    sync(D, ports, store, api, now=AFTER)
    assert len(details(store)) == 2


def test_api_errors_keep_only_the_code():
    def reject(req, timeout):
        body = io.BytesIO(json.dumps({"error": {"code": "invalid_phone", "message": "bad +919876543210"}}).encode())
        raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable", {}, body)
    with pytest.raises(RuntimeError) as e:
        SarvamCampaigns(env=ENV, opener=reject).create_campaign("x", D, 1, "09:00", "11:00", 1, 30)
    assert "422 invalid_phone" in str(e.value) and "9876543210" not in str(e.value)


def test_campaign_task_runs_daily_push_and_one_extra_day(tmp_path):
    xml = task_xml(D, 4, "08:30", r"C:\Python\python.exe", tmp_path, mode="campaign")
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    root = ET.fromstring(xml.split("?>", 1)[1])
    trig = root.find("t:Triggers/t:CalendarTrigger", ns)
    assert trig.find("t:StartBoundary", ns).text == "2026-10-27T08:30:00"
    assert trig.find("t:EndBoundary", ns).text == "2026-10-31T23:59:59"
    assert "weathercall.campaign daily" in root.find("t:Actions/t:Exec/t:Arguments", ns).text
