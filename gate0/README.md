# Gate Zero: Morning Weather Call

Every morning, call each consented farmer once in their language (Hindi, Kannada, Telugu or English), give today's
weather for their village (temperature, wind, chance of rain, humidity), ask if they understood, and end politely.
Standalone: no Trust AI, no farming advice, weather only.

## How it works

1. **Farmers** come from a CSV (Farmer ID, Name, Mobile, Village, District, State, Language, Consent) imported in the
   dashboard. Only consented, active farmers with a phone number are called, once per day.
2. **Weather** comes from Open-Meteo for the farmer's village (district centre if the village is not found). The 7-day
   forecast is saved; if the provider fails it is retried (+15, +45, +105 min), then the saved forecast is used.
3. **The call** is placed through a Sarvam voice agent. The agent greets the farmer, asks if it is a good time, gives the
   weather from the variables we send, answers weather questions only, and ends with a goodbye. It never claims to be human.
4. **Results** (summary, whether the farmer understood, callback time, transcript) are read back from Sarvam and shown in
   the dashboard. A farmer who asks for a later time gets one callback at that time (5 am to 10 pm), never retried.

Decisions and the rules behind them are in `docs/DECISIONS.md`. Sarvam setup is in `docs/SARVAM_SETUP.md`.

## Run it

```bash
cd gate0
npm --prefix frontend install
npm run backend        # Python API on http://127.0.0.1:8000  (reads gate0/.env)
npm run frontend       # dashboard on http://localhost:5173
```

Without a complete Sarvam setup in `.env` the backend runs in **simulated** mode: no real calls, results marked
"simulated". Never commit `.env`, farmer files or databases.

## Tests

```bash
cd gate0/backend
pip install -r requirements.txt
python -m pytest -q
```

The Python commands in the docs (`python -m weathercall.cli`, `python -m weathercall.campaign`) run from `gate0/backend`.

## Layout

```text
gate0/
├── backend/
│   ├── weathercall/   engine, contracts, ports, script, adapters (Sarvam, Open-Meteo, sheet, SQLite), service.py, server.py
│   └── tests/
├── frontend/          React dashboard (see frontend/README.md)
└── docs/              DECISIONS.md, SARVAM_SETUP.md, INTEGRATION.md
```

The core (`contracts.py`, `ports.py`, `engine.py`, `script.py`, `config.py`) never imports an adapter, a database or a
provider SDK; everything external sits behind a port in `adapters/`. A test enforces this.
