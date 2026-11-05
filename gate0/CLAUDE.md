# CLAUDE.md — Gate Zero (weather call prototype)

## Goal
Every morning, call each consented farmer once (30 to 40 seconds, Hindi or English), say the voice is an AI, and give today's weather. Done by 15 Nov 2026. Standalone: no Trust AI, no advice, weather only.

## Design rule that matters most
Build it so it can merge into the final product. The core (`contracts.py`, `ports.py`, `engine.py`, `script.py`, `config.py`) must never import an adapter, a database or a provider SDK. Everything external goes through a port in `ports.py` and lives in `weathercall/adapters/`. A test enforces this.

## Hard rules
1. Only consented, active farmers are called. Anyone else is skipped and the reason recorded.
2. The opening message does not announce that the voice is an AI (team decision, 2 Nov 2026), but the agent never claims to be human and says honestly that it is automated if a farmer sincerely asks.
3. No phone numbers, farmer details or provider keys in git, logs, status views or error messages.
4. One call outcome per farmer per day, never dialled twice for the same day (idempotent).
5. A provider failure must never stop the morning run.
6. Hindi wording is a draft until a native speaker reviews it.

## Unconfirmed with the client (placeholders in `config.py`)
Retries, wait between attempts, call time, what to do when weather is missing. Do not hard-wire them; keep them settings.

## Commands
```
cd backend
python -m pytest -q
python -m weathercall.cli --date 2026-11-05
```

## Adding a real provider
Write one adapter class that satisfies the port, register it in `adapters/__init__.py`, add a test, and choose it in `.env`. Do not touch the engine.
