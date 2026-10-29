"""Standalone utility and live rehearsal tool to verify Open-Meteo forecasts and populate SQLite ledger.

Usage:
    python -m weathercall.weather_check [--place Bidar] [--lat 17.9104] [--lon 77.5199] [--date YYYY-MM-DD] [--db PATH]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sqlite3
import sys
from datetime import date

from .adapters.open_meteo import OpenMeteoWeather
from .config import load_env
from .contracts import FarmerContext, Language
from .script import build_message


def run_weather_check(
    place: str = "Bidar",
    lat: float = 17.9104,
    lon: float = 77.5199,
    target_date: date | None = None,
    db_path: str | None = None,
) -> int:
    load_env()
    if target_date is None:
        target_date = date.today()

    if db_path is None:
        env_db = os.environ.get("GATE0_DB") or os.environ.get("WEATHER_DB_PATH")
        if env_db:
            db_path = env_db
        else:
            here = pathlib.Path(__file__).resolve().parent.parent
            db_path = str(here / "weathercall.db")

    print(f"=== Agrythm Gate Zero: Weather Check & Live Rehearsal ===")
    print(f"Target Place: {place} ({lat:.4f}, {lon:.4f})")
    print(f"Target Date:  {target_date.isoformat()}")
    print(f"Target DB:    {db_path}")

    # 1. Fetch live forecast using Open-Meteo adapter (auto-stores upcoming days in DB)
    adapter = OpenMeteoWeather(db_path=db_path)
    report = adapter.get_weather(place, lat, lon, target_date)

    if report is None:
        print("[ERROR] Weather fetch failed and no cached forecast exists in database.")
        return 1

    print("\n[SUCCESS] WeatherReport received:")
    print(f"  Source:       {report.source}")
    print(f"  Summary:      {report.summary}")
    print(f"  Temp Min:     {report.temp_min_c}\u00b0C")
    print(f"  Temp Max:     {report.temp_max_c}\u00b0C")
    print(f"  Rain Chance:  {report.rain_chance_pct}%")

    # 2. Spoken voice preview in English & Hindi
    dummy_en = FarmerContext("PREVIEW_EN", "Farmer", Language.EN, place, lat, lon, True, True, "")
    dummy_hi = FarmerContext("PREVIEW_HI", "किसान भाई", Language.HI, place, lat, lon, True, True, "")
    print("\nSpoken Message Previews:")
    print(f"  [EN] {build_message(dummy_en, report)}")
    try:
        print(f"  [HI] {build_message(dummy_hi, report)}")
    except UnicodeEncodeError:
        print("  [HI] (Devanagari text omitted to preserve cp1252 console encoding)")

    # 3. Read back and verify cached forecast rows stored in DB (including upcoming days)
    print(f"\n[VERIFIED] Stored Forecast Records in SQLite 'weather' table ({db_path}):")
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT forecast_date, summary, temp_min_c, temp_max_c, rain_chance_pct, source, fetched_at "
                "FROM weather WHERE place_name=? ORDER BY forecast_date ASC",
                (place,),
            ).fetchall()
            for r in rows:
                print(f"  Date: {r[0]} | {r[1]:<14} | Min: {r[2]}°C | Max: {r[3]}°C | Rain: {r[4]}% | Source: {r[5]}")
    except Exception as exc:
        print(f"  [WARNING] Could not query database rows: {exc}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live dry-run check for Open-Meteo weather adapter.")
    parser.add_argument("--place", default="Bidar", help="Place or village name")
    parser.add_argument("--lat", type=float, default=17.9104, help="Latitude")
    parser.add_argument("--lon", type=float, default=77.5199, help="Longitude")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="Forecast date (YYYY-MM-DD)")
    parser.add_argument("--db", default=None, help="SQLite database path")

    args = parser.parse_args(argv)
    return run_weather_check(
        place=args.place,
        lat=args.lat,
        lon=args.lon,
        target_date=args.date,
        db_path=args.db,
    )


if __name__ == "__main__":
    sys.exit(main())
