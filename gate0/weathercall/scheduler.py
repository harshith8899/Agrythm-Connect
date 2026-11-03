"""APScheduler setup for the 9:00 AM IST Daily Farmer Call Dispatcher (ACK-17).

Configures and manages daily scheduling using APScheduler with Asia/Kolkata timezone,
unique job registration (daily_farmer_dispatcher), and duplicate prevention.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
from datetime import date
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import load_env
from .contracts import DispatchSummary
from .dispatcher import DailyFarmerDispatcher

if TYPE_CHECKING:
    from .engine import Ports

logger = logging.getLogger("weathercall.scheduler")

JOB_ID = "daily_farmer_dispatcher"
DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_HOUR = 9
DEFAULT_MINUTE = 0


def get_schedule_config() -> tuple[int, int, str]:
    """Load hour, minute, and timezone from environment or defaults."""
    load_env()
    hour = int(os.environ.get("GATE0_DISPATCH_HOUR", DEFAULT_HOUR))
    minute = int(os.environ.get("GATE0_DISPATCH_MINUTE", DEFAULT_MINUTE))
    tz_str = os.environ.get("GATE0_TIMEZONE", DEFAULT_TIMEZONE)
    return hour, minute, tz_str


def create_scheduler(
    dispatcher: DailyFarmerDispatcher | None = None,
    hour: int | None = None,
    minute: int | None = None,
    tz_name: str | None = None,
    blocking: bool = False,
) -> BaseScheduler:
    """Create and configure APScheduler instance for the 9:00 AM IST daily call job.

    Uses replace_existing=True to avoid duplicate job registration.
    """
    cfg_hour, cfg_minute, cfg_tz = get_schedule_config()
    final_hour = hour if hour is not None else cfg_hour
    final_minute = minute if minute is not None else cfg_minute
    final_tz = tz_name if tz_name is not None else cfg_tz

    tz = ZoneInfo(final_tz)
    disp = dispatcher or DailyFarmerDispatcher()

    scheduler = BlockingScheduler() if blocking else BackgroundScheduler()

    trigger = CronTrigger(
        hour=final_hour,
        minute=final_minute,
        timezone=tz,
    )

    scheduler.add_job(
        func=disp.dispatch_daily_calls,
        trigger=trigger,
        id=JOB_ID,
        name="Daily Farmer Weather Call Dispatcher (Bidar)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    logger.info(
        f"[SCHEDULER-INIT] Configured job '{JOB_ID}' at {final_hour:02d}:{final_minute:02d} {final_tz} "
        f"(Scheduler type: {'Blocking' if blocking else 'Background'})"
    )
    return scheduler


def run_dispatcher_now(
    call_date: date | None = None,
    ports: Ports | None = None,
) -> DispatchSummary:
    """Trigger the daily farmer call dispatcher immediately for testing or operational runs."""
    dispatcher = DailyFarmerDispatcher(ports=ports)
    return dispatcher.dispatch_daily_calls(call_date=call_date)


def start_scheduler_process(
    hour: int | None = None,
    minute: int | None = None,
    tz_name: str | None = None,
) -> None:
    """Run the scheduler as a standalone persistent foreground process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    scheduler = create_scheduler(
        hour=hour,
        minute=minute,
        tz_name=tz_name,
        blocking=True,
    )

    def _shutdown(signum, frame):
        logger.info(f"Received signal {signum}. Shutting down daily farmer scheduler...")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    cfg_hour, cfg_minute, cfg_tz = get_schedule_config()
    final_hour = hour if hour is not None else cfg_hour
    final_minute = minute if minute is not None else cfg_minute
    final_tz = tz_name if tz_name is not None else cfg_tz

    print(
        f"==========================================================\n"
        f" Agrythm Connect: 9:00 AM Daily Farmer Call Scheduler\n"
        f" Scheduled: Every day at {final_hour:02d}:{final_minute:02d} ({final_tz})\n"
        f" Target: Bidar, Karnataka (17.9104, 77.5199)\n"
        f" Press Ctrl+C to terminate\n"
        f"=========================================================="
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler terminated.")

