"""Calls scheduled and dialled by Sarvam Campaigns. Our side only decides who and what, then records results.

    python -m weathercall.campaign create --start 2026-10-27 --days 4 [--time 09:00] [--window-end 11:00]
    python -m weathercall.campaign push   [--date D]   check today's farmers and hand the eligible ones to Sarvam
    python -m weathercall.campaign sync   [--date D]   pull that day's outcomes from Sarvam into the ledger
    python -m weathercall.campaign daily  [--date D]   sync yesterday, then push today (what the 08:30 task runs)
    python -m weathercall.campaign status [--date D]

Every check (already handled, active, consent, phone, weather saved) is the engine's prepare_call, the same one
direct dialling uses. A farmer is pushed at most once per day, and only with complete weather.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .adapters import build_ports
from .adapters.sarvam_agent import _LANG_NAMES
from .adapters.sarvam_campaign import IST, CampaignStore, QueuedCall, SarvamCampaigns, outcome, scrub
from .cli import ENV_FILE, load_env_file
from .config import Settings
from .contracts import AttemptStatus, CallAttempt, CallRequest, FarmerDayResult, FinalResult, Language
from .engine import Ports, final_result, prepare_call
from .script import format_now, weather_variables


def push(day: date, ports: Ports, settings: Settings, store: CampaignStore, api: SarvamCampaigns,
         now: datetime | None = None) -> list[str]:
    camp = store.campaign_for(day)
    if camp is None:
        return [f"{day}: no Sarvam campaign covers this day; run 'campaign create' first"]
    already = store.queued_ids(day)
    now_text = format_now(now or datetime.now(IST))      # lets the agent confirm a callback's day and time
    calls, rows, skipped = [], [], 0
    for fid in ports.farmers.list_callable_ids(day):
        if fid in already:
            continue
        prepared = prepare_call(CallRequest(fid, day, requested_by="scheduler"), ports, settings)
        if isinstance(prepared, FarmerDayResult):
            skipped += 1
            continue
        f = prepared.farmer
        calls.append(QueuedCall(f.farmer_id, f.phone, _LANG_NAMES[f.language], prepared.message,
                                weather_variables(f, prepared.weather, now_text)))
        rows.append((f.farmer_id, f.language.value, prepared.message, prepared.weather.source))
    if calls:
        cohort_ids = api.stream_cohort(camp["campaign_id"], f"gate0-{day.isoformat()}-{datetime.now():%H%M}", calls)
        store.mark_queued(day, camp["campaign_id"], cohort_ids[0], rows)
    return [f"{day}: pushed {len(calls)} farmer(s) to Sarvam campaign {camp['campaign_id']}; "
            f"skipped {skipped}; already queued earlier {len(already)}"]


def sync(day: date, ports: Ports, store: CampaignStore, api: SarvamCampaigns, now: datetime | None = None) -> list[str]:
    camp = store.campaign_for(day)
    queued = store.queued(day)
    if camp is None or not queued:
        return [f"{day}: nothing queued with Sarvam for this day"]
    now = now or datetime.now(IST)
    window_over = now > datetime.combine(day, time.fromisoformat(camp["window_end"]), IST) + timedelta(hours=1)
    by_farmer: dict[str, list[dict]] = {}
    for item in api.attempts(camp["campaign_id"], day):
        by_farmer.setdefault(item.get("user_identifier") or "", []).append(item)

    done = pending = detail_rows = transcript_errors = 0
    for fid, q in queued.items():
        if ports.ledger.has_final_result(fid, day):
            continue
        settled = sorted((i for i in by_farmer.get(fid, []) if outcome(i)), key=lambda i: i.get("retry_attempt") or 0)
        answered = next((n for n, i in enumerate(settled) if outcome(i) is AttemptStatus.ANSWERED), None)
        if answered is not None:
            settled = settled[:answered + 1]
        elif not settled or settled[-1].get("next_action_status") == "retry":
            if window_over and not settled:      # Sarvam never dialled within the window
                ports.ledger.record_day_result(FarmerDayResult(fid, day, FinalResult.FAILED, 0))
                done += 1
            else:
                pending += 1
            continue
        for n, i in enumerate(settled, start=1):
            reason = i.get("failure_reason") or ""
            ports.ledger.record_attempt(CallAttempt(
                farmer_id=fid, call_date=day, attempt_no=n, status=outcome(i), language=Language(q["language"]),
                message_text=q["message"], provider_call_id=i.get("attempt_id") or "",
                duration_s=int(i.get("duration_in_seconds") or 0),
                error="" if reason in ("", "NO_FAILURE_REASON") else scrub(reason)[:80],
                weather_source=q["weather_source"]))
            transcript = None
            if outcome(i) is AttemptStatus.ANSWERED and i.get("interaction_id"):
                try:
                    transcript = api.transcript(i["interaction_id"])
                except Exception:  # a missing transcript must not lose the call's other details
                    transcript_errors += 1
            store.save_detail(fid, day, i.get("attempt_id") or f"attempt-{n}", i.get("interaction_id"),
                              i.get("ended_by"), reason, i.get("call_summary"), transcript)
            detail_rows += 1
        ports.ledger.record_day_result(FarmerDayResult(fid, day, final_result(outcome(settled[-1])), len(settled)))
        done += 1
    return [f"{day}: synced {done} result(s) from Sarvam; still in progress {pending}; "
            f"details {detail_rows}; transcript errors {transcript_errors}"]


def _summary(day: date, ports: Ports) -> list[str]:
    v = ports.ledger.status(day)
    lines = [f"{v.call_date}: total {v.total} | answered {v.answered} | unanswered {v.unanswered} "
             f"| failed {v.failed} | skipped {v.skipped}"]
    for r in v.rows:
        extra = f" ({r.skip_reason.value})" if r.skip_reason else f" after {r.attempts} attempt(s)"
        lines.append(f"  {r.farmer_id}  {r.result.value}{extra}")
    return lines


def main(argv: list[str] | None = None, env_file: Path | None = ENV_FILE) -> int:
    p = argparse.ArgumentParser(description="Gate Zero calls through Sarvam Campaigns")
    p.add_argument("cmd", choices=["create", "push", "sync", "daily", "status"])
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--start", type=date.fromisoformat, help="create: first call day")
    p.add_argument("--days", type=int, default=4, help="create: number of days")
    p.add_argument("--time", help="create: daily start of calling (default GATE0_CALL_TIME)")
    p.add_argument("--window-end", help="create: daily end of calling (default SARVAM_CALL_WINDOW_END or 11:00)")
    p.add_argument("--log-dir", help="also append output to <dir>/campaign-YYYY-MM-DD.log")
    a = p.parse_args(argv)
    if env_file:
        load_env_file(env_file)
    day = a.date or datetime.now(IST).date()
    settings = Settings.from_env()

    try:
        ports = build_ports()
        store = CampaignStore(os.environ.get("GATE0_DB", ":memory:"))
        api = SarvamCampaigns()
        if a.cmd == "create":
            start = a.start or day + timedelta(days=1)
            call_time = a.time or settings.call_time
            window_end = a.window_end or os.environ.get("SARVAM_CALL_WINDOW_END", "11:00")
            if a.days < 1 or time.fromisoformat(window_end) <= time.fromisoformat(call_time):
                raise ValueError("--days must be at least 1 and the window must end after it starts")
            cid = api.create_campaign(f"Gate0 weather {start.isoformat()}", start, a.days, call_time, window_end,
                                      settings.max_attempts, settings.retry_gap_minutes)
            store.save_campaign(cid, start, a.days, call_time, window_end)
            lines = [f"Created Sarvam campaign {cid}: {a.days} day(s) from {start}, calls {call_time}-{window_end} IST, "
                     f"up to {settings.max_attempts} attempt(s) {settings.retry_gap_minutes} min apart.",
                     "Each day's farmers are added by 'campaign daily' (schedule it before the window opens)."]
        elif a.cmd == "push":
            lines = push(day, ports, settings, store, api)
        elif a.cmd == "sync":
            lines = sync(day, ports, store, api) + _summary(day, ports)
        elif a.cmd == "daily":
            yesterday = day - timedelta(days=1)
            lines = (sync(yesterday, ports, store, api) if store.campaign_for(yesterday) else [])
            lines += push(day, ports, settings, store, api)
        else:
            camp = store.campaign_for(day)
            lines = [f"campaign: {camp['campaign_id']} from {camp['start']} for {camp['days']} day(s), "
                     f"{camp['call_time']}-{camp['window_end']} IST" if camp else "campaign: none covers this day",
                     f"queued today: {len(store.queued_ids(day))}"] + _summary(day, ports)
        code = 0
    except Exception as exc:  # our messages never carry phone numbers; HTTP errors show only status and URL path
        lines, code = [f"{day}: campaign {a.cmd} failed: {type(exc).__name__}: {exc}"], 1

    print("\n".join(lines))
    if a.log_dir:
        log = Path(a.log_dir)
        log.mkdir(parents=True, exist_ok=True)
        with (log / f"campaign-{day.isoformat()}.log").open("a", encoding="utf-8") as fh:
            fh.write(f"--- {datetime.now().isoformat(timespec='seconds')} {a.cmd}\n" + "\n".join(lines) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
