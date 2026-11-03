"""CLI entry points for Gate Zero call operations and scheduler.

Usage:
    python -m weathercall.cli [--date YYYY-MM-DD]
    python -m weathercall.cli --dispatch-now [--date YYYY-MM-DD]
    python -m weathercall.cli --dispatch-now --phone +91XXXXXXXXXX [--lang kn|hi|en] [--name NAME]
    python -m weathercall.cli --start-scheduler
"""
from __future__ import annotations

import argparse
import time
from datetime import date

from .adapters import build_ports
from .adapters.local import InMemoryFarmerSource
from .config import Settings
from .contracts import FarmerContext, Language, WeatherReport
from .dispatcher import BIDAR_LAT, BIDAR_LON, BIDAR_PLACE, DailyFarmerDispatcher
from .engine import run_morning
from .scheduler import start_scheduler_process


def _print_weather_details(w: WeatherReport | None, weather_fetched: bool) -> None:
    """Print complete weather details inside the dispatch execution summary."""
    if not weather_fetched or w is None:
        print("Weather Details:    Unavailable (fetch failed or aborted)")
        return
    print("Weather Details:")
    print(f"  Place:            {w.place_name} ({BIDAR_LAT:.4f}\u00b0N, {BIDAR_LON:.4f}\u00b0E)")
    print(f"  Summary:          {w.summary.capitalize()}")
    print(f"  Temperature:      {w.temp_min_c}\u00b0C min / {w.temp_max_c}\u00b0C max")
    print(f"  Rain Chance:      {w.rain_chance_pct}%")
    print(f"  Wind Speed:       {w.wind_speed_kmh} km/h")
    print(f"  Humidity:         {w.humidity_pct}%")
    print(f"  Source:           {w.source}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gate Zero weather call and daily dispatcher operations")
    p.add_argument("--date", type=date.fromisoformat, default=date.today(), help="Target run date (YYYY-MM-DD)")
    p.add_argument("--dispatch-now", action="store_true", help="Execute 9:00 AM Daily Farmer Call Dispatcher immediately")
    p.add_argument("--start-scheduler", action="store_true", help="Start the persistent daily call scheduler process")
    p.add_argument("--phone", type=str, default=None, help="Target specific phone number to test (e.g. +91XXXXXXXXXX)")
    p.add_argument("--name", type=str, default="Farmer", help="Farmer display name for voice greeting (default: Farmer)")
    p.add_argument("--lang", type=str, default="kn", choices=["kn", "hi", "en"], help="Preferred language: kn, hi, en (default: kn)")
    a = p.parse_args(argv)

    if a.start_scheduler:
        start_scheduler_process()
        return 0

    if a.phone or a.dispatch_now:
        ports = build_ports()

        # If a specific phone number is provided for testing, dispatch specifically to this farmer
        if a.phone:
            raw_phone = a.phone.strip()
            formatted_phone = f"+91{raw_phone}" if len(raw_phone) == 10 and not raw_phone.startswith("+") else raw_phone
            lang_enum = Language(a.lang)
            test_fid = f"TEST_{abs(hash(formatted_phone)) % 10000}_{int(time.time())}"
            test_farmer = FarmerContext(
                farmer_id=test_fid,
                display_name=a.name,
                language=lang_enum,
                place_name=BIDAR_PLACE,
                latitude=BIDAR_LAT,
                longitude=BIDAR_LON,
                consent=True,
                active=True,
                phone=formatted_phone,
            )
            ports.farmers = InMemoryFarmerSource([test_farmer])

            dispatcher = DailyFarmerDispatcher(ports=ports)
            summary = dispatcher.dispatch_daily_calls(call_date=a.date)
            print(f"\n=== Single Farmer Dispatch Test ({formatted_phone}) ===")
            print(f"Status:             {summary.status}")
            print(f"Language:           {lang_enum.value.upper()} ({a.lang})")
            print(f"Duration:           {summary.duration_s:.2f}s")
            _print_weather_details(summary.weather_report, summary.weather_fetched)
            print(f"Submitted Calls:    {summary.submitted}")
            print(f"Failed Calls:       {summary.failed}")
            if summary.details:
                d = summary.details[0]
                print(f"Call Status:        {d.get('status')}")
                print(f"Provider Call ID:   {d.get('provider_call_id')}")
            return 0 if summary.failed == 0 else 1

        dispatcher = DailyFarmerDispatcher(ports=ports)
        summary = dispatcher.dispatch_daily_calls(call_date=a.date)
        print(f"\n=== Dispatch Execution Summary ({summary.dispatch_date.isoformat()}) ===")
        print(f"Status:             {summary.status}")
        print(f"Duration:           {summary.duration_s:.2f}s")
        _print_weather_details(summary.weather_report, summary.weather_fetched)
        print(f"Total Eligible:     {summary.total_eligible}")
        print(f"Submitted Calls:    {summary.submitted}")
        print(f"Failed Calls:       {summary.failed}")
        print(f"Skipped Duplicates: {summary.skipped_duplicates}")
        print(f"Skipped Ineligible: {summary.skipped_ineligible}")
        return 0 if summary.failed == 0 else 1

    ports = build_ports()
    view = run_morning(a.date, ports, Settings.from_env())
    print(f"{view.call_date}: total {view.total} | answered {view.answered} | unanswered {view.unanswered} "
          f"| failed {view.failed} | skipped {view.skipped}")
    for r in view.rows:
        extra = f" ({r.skip_reason.value})" if r.skip_reason else f" after {r.attempts} attempt(s)"
        print(f"  {r.farmer_id}  {r.result.value}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
