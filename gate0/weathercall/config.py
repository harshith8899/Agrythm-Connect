"""Settings from environment. Defaults are placeholders until confirmed with the client."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass


def load_env(env_path: str | os.PathLike[str] | None = None) -> None:
    """Load key-value pairs from .env into os.environ if not already set."""
    if env_path is None:
        candidates = [
            pathlib.Path.cwd() / ".env",
            pathlib.Path(__file__).resolve().parent.parent / ".env",
            pathlib.Path(__file__).resolve().parent.parent.parent / ".env",
        ]
    else:
        candidates = [pathlib.Path(env_path)]

    for p in candidates:
        if p.is_file():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
                        v = v[1:-1]
                    if k and k not in os.environ:
                        os.environ[k] = v
                break
            except Exception:
                pass


@dataclass(frozen=True)
class Settings:
    max_attempts: int = 3               # UNCONFIRMED with client
    retry_gap_minutes: int = 30         # UNCONFIRMED with client
    call_time: str = "07:00"            # UNCONFIRMED with client
    on_weather_missing: str = "skip"    # skip | (other behaviours to be agreed)
    target_seconds_min: int = 30
    target_seconds_max: int = 40

    @classmethod
    def from_env(cls) -> "Settings":
        load_env()
        g = os.environ.get
        return cls(
            max_attempts=int(g("GATE0_MAX_ATTEMPTS", cls.max_attempts)),
            retry_gap_minutes=int(g("GATE0_RETRY_GAP_MINUTES", cls.retry_gap_minutes)),
            call_time=g("GATE0_CALL_TIME", cls.call_time),
            on_weather_missing=g("GATE0_ON_WEATHER_MISSING", cls.on_weather_missing),
        )
