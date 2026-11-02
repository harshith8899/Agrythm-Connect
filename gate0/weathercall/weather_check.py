"""Fetch and store today's weather for every farmer, without calling anyone.

    python -m weathercall.weather_check [--date YYYY-MM-DD]

Shows, per farmer, which place was matched and the stored weather, or that the farmer will be skipped.
The morning run then reuses the stored weather. Output stays on screen (it names places), not in run logs.
"""
from __future__ import annotations

import argparse
from datetime import date

from .adapters import build_ports
from .cli import ENV_FILE, load_env_file


def main(argv: list[str] | None = None, env_file=ENV_FILE) -> int:
    p = argparse.ArgumentParser(description="Check and store weather for today's farmers (no calls)")
    p.add_argument("--date", type=date.fromisoformat, default=None)
    a = p.parse_args(argv)
    if env_file:
        load_env_file(env_file)
    day = a.date or date.today()
    ports = build_ports()
    matches = getattr(ports.farmers, "matches", {})
    ready = 0
    ids = ports.farmers.list_callable_ids(day)
    print(f"Weather for {day} (source: {type(getattr(ports.weather, 'inner', ports.weather)).__name__})")
    for fid in ids:
        f = ports.farmers.get_context(fid)
        if f is None:
            continue
        w = ports.weather.get_weather(f.place_name, f.latitude, f.longitude, day)
        where = matches.get(fid, f"{f.latitude}, {f.longitude}")
        if w is None:
            print(f"  {fid}  {f.place_name:<14} {where}\n        NO WEATHER -> will not be called")
            continue
        ready += 1
        print(f"  {fid}  {f.place_name:<14} {where}\n        {w.temp_min_c}-{w.temp_max_c} C, wind {w.wind_kmh} km/h, "
              f"rain {w.rain_chance_pct}%, humidity {w.humidity_pct}%  [{w.source}]")
    errors = getattr(ports.weather, "provider_errors", 0)
    print(f"{ready} of {len(ids)} farmers have weather" + (f"; {errors} provider error(s)" if errors else "")
          + (f"; {fb} from a saved earlier forecast" if (fb := getattr(ports.weather, "fallbacks", 0)) else ""))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
