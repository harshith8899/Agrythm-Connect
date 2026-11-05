"""Trigger for the morning run, using Windows Task Scheduler.

    python -m weathercall.schedule activate --start 2026-10-27 --days 4 [--time 09:00] [--mode direct|campaign]
    python -m weathercall.schedule status
    python -m weathercall.schedule deactivate

direct   (default) the task runs the CLI daily at the call time; our code dials. Expires after the last day.
campaign the task runs 'campaign daily' 30 minutes before the call time: it syncs yesterday's results and hands
         today's eligible farmers to the Sarvam campaign, which then dials in its own window. It runs one extra
         day so the last day's results are synced. Create the campaign first ('campaign create').
Both modes check the campaign window themselves, so a stray run outside it does nothing. Logs: gate0/logs/.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from .cli import ENV_FILE, load_env_file
from .config import Settings

TASK_NAME = "Agrythm Gate0 Weather Call"
GATE0_DIR = Path(__file__).resolve().parent.parent.parent


def task_xml(start: date, days: int, call_time: str, python: str, workdir: Path, mode: str = "direct") -> str:
    at = time.fromisoformat(call_time)
    first = datetime.combine(start, at)
    run_days = days + 1 if mode == "campaign" else days     # campaign: one more morning to sync the last day
    last_day_end = datetime.combine(start + timedelta(days=run_days - 1), time(23, 59, 59))
    if mode == "campaign":
        args = f'-m weathercall.campaign daily --log-dir "{workdir / "logs"}"'
    else:
        args = (f"-m weathercall.cli --window-start {start.isoformat()} --window-days {days} "
                f'--log-dir "{workdir / "logs"}"')
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Gate Zero weather call: daily at {escape(call_time)} for {days} day(s) from {start.isoformat()}</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{first.isoformat(timespec="seconds")}</StartBoundary>
      <EndBoundary>{last_day_end.isoformat(timespec="seconds")}</EndBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>false</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(python)}</Command>
      <Arguments>{escape(args)}</Arguments>
      <WorkingDirectory>{escape(str(workdir))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def preflight(mode: str = "direct", start: date | None = None) -> list[str]:
    """Check the setup the scheduled run will use. Returns warnings; raises if the farmer sheet cannot load."""
    from .adapters import build_ports
    load_env_file(ENV_FILE)
    g = os.environ.get
    ports = build_ports()
    ids = ports.farmers.list_callable_ids(date.today())
    farmers = [ports.farmers.get_context(i) for i in ids]
    callable_ = [f for f in farmers if f and f.active and f.consent and f.phone]
    print(f"farmers: {len(ids)} in source, {len(callable_)} consented, active and with a phone")
    warn = []
    if g("GATE0_FARMERS", "local") == "local":
        warn.append("GATE0_FARMERS=local: the 10 fake demo farmers will be used, not your sheet")
    if mode == "campaign":
        from .adapters.sarvam_campaign import CampaignStore
        if start and CampaignStore(g("GATE0_DB", ":memory:")).campaign_for(start) is None:
            warn.append(f"no Sarvam campaign covers {start}: run 'python -m weathercall.campaign create' first")
    else:
        if g("GATE0_VOICE", "mock") == "mock":
            warn.append("GATE0_VOICE=mock: no audio will be generated (set GATE0_VOICE=sarvam_agent)")
        if g("GATE0_TELEPHONY", "mock") == "mock":
            warn.append("GATE0_TELEPHONY=mock: no phone will ring; outcomes are simulated")
    if g("GATE0_WEATHER", "mock") == "mock":
        warn.append("GATE0_WEATHER=mock: only Mandya, Hassan and Mysuru have weather; others are skipped")
    if g("GATE0_LEDGER", "local") == "local" and g("GATE0_DB", ":memory:") == ":memory:":
        warn.append("GATE0_DB is in memory: results are lost after each run (set GATE0_DB=weathercall.db)")
    return warn


def _schtasks(*args: str) -> int:
    return subprocess.run(["schtasks", *args]).returncode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Activate or remove the daily Gate Zero trigger (Windows)")
    sub = p.add_subparsers(dest="cmd", required=True)
    act = sub.add_parser("activate")
    act.add_argument("--start", type=date.fromisoformat, help="first call day (default: tomorrow)")
    act.add_argument("--days", type=int, default=4)
    act.add_argument("--time", help="HH:MM the task runs (default: GATE0_CALL_TIME; campaign: 30 min before it)")
    act.add_argument("--mode", choices=["direct", "campaign"], default=None,
                     help="direct: we dial; campaign: Sarvam dials (default: GATE0_CALL_MODE or direct)")
    sub.add_parser("status")
    sub.add_parser("deactivate")
    a = p.parse_args(argv)

    if sys.platform != "win32":
        print("This trigger uses Windows Task Scheduler. On Linux use cron, e.g. "
              "'0 9 * * * cd gate0 && python -m weathercall.cli --window-start ... --window-days 4 --log-dir logs'")
        return 1
    if a.cmd == "status":
        return _schtasks("/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST")
    if a.cmd == "deactivate":
        return _schtasks("/Delete", "/TN", TASK_NAME, "/F")

    load_env_file(ENV_FILE)
    mode = a.mode or os.environ.get("GATE0_CALL_MODE", "direct")
    start = a.start or date.today() + timedelta(days=1)
    if a.days < 1:
        p.error("--days must be at least 1")
    for w in preflight(mode, start):
        print(f"warning: {w}")
    call_time = a.time or Settings.from_env().call_time
    if mode == "campaign" and not a.time:
        call_time = (datetime.combine(start, time.fromisoformat(call_time)) - timedelta(minutes=30)).strftime("%H:%M")
    xml = task_xml(start, a.days, call_time, sys.executable, GATE0_DIR, mode)
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "task.xml"
        f.write_text(xml, encoding="utf-16")
        code = _schtasks("/Create", "/TN", TASK_NAME, "/XML", str(f), "/F")
    if code == 0:
        end = start + timedelta(days=a.days if mode == "campaign" else a.days - 1)
        what = "hands farmers to Sarvam" if mode == "campaign" else "calls farmers"
        print(f"Activated ({mode}): '{TASK_NAME}' {what} daily at {call_time} from {start} to {end}. "
              f"Logs: {GATE0_DIR / 'logs'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
