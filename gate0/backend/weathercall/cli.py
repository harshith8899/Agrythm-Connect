"""Run one morning cycle: python -m weathercall.cli [--date YYYY-MM-DD] [--window-start D --window-days N] [--log-dir DIR]

Reads gate0/.env first (values already in the environment win). The scheduled task passes a window so that a
run outside the agreed days does nothing.
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from .adapters import build_ports
from .config import Settings
from .engine import run_morning

_default_env = Path(__file__).resolve().parent.parent / ".env"
ENV_FILE = _default_env if _default_env.exists() else Path(__file__).resolve().parent.parent.parent / ".env"


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.split(" #", 1)[0].strip().strip('"').strip("'")   # drop inline comments
            os.environ.setdefault(k.strip(), v)


def in_window(day: date, start: date | None, days: int | None) -> bool:
    if start is None:
        return True
    return start <= day < start + timedelta(days=days or 1)


def main(argv: list[str] | None = None, env_file: Path | None = ENV_FILE) -> int:
    p = argparse.ArgumentParser(description="Gate Zero morning weather call (mock providers by default)")
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--window-start", type=date.fromisoformat, help="first day of the calling campaign")
    p.add_argument("--window-days", type=int, help="number of days in the campaign")
    p.add_argument("--log-dir", help="also append the summary to <dir>/run-YYYY-MM-DD.log")
    a = p.parse_args(argv)
    if env_file:
        load_env_file(env_file)
    day = a.date or date.today()

    lines: list[str] = []
    if not in_window(day, a.window_start, a.window_days):
        lines.append(f"{day}: outside campaign window starting {a.window_start} for {a.window_days} day(s); nothing to do")
        code = 0
    else:
        try:
            view = run_morning(day, build_ports(), Settings.from_env())
            lines.append(f"{view.call_date}: total {view.total} | answered {view.answered} | unanswered {view.unanswered} "
                         f"| failed {view.failed} | skipped {view.skipped}")
            for r in view.rows:
                extra = f" ({r.skip_reason.value})" if r.skip_reason else f" after {r.attempts} attempt(s)"
                lines.append(f"  {r.farmer_id}  {r.result.value}{extra}")
            code = 0
        except Exception as exc:  # setup errors (bad sheet, missing key); our messages never carry phone numbers
            lines.append(f"{day}: run did not start: {type(exc).__name__}: {exc}")
            code = 1

    print("\n".join(lines))
    if a.log_dir:
        log = Path(a.log_dir)
        log.mkdir(parents=True, exist_ok=True)
        with (log / f"run-{day.isoformat()}.log").open("a", encoding="utf-8") as fh:
            fh.write(f"--- {datetime.now().isoformat(timespec='seconds')}\n" + "\n".join(lines) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
