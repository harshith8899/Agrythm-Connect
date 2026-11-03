# Agrythm Connect

Voice-first farmer relationship and execution layer. This repository holds three areas of work, each in its own folder.

| Folder | What it is | Status |
|---|---|---|
| [`Pilot/`](Pilot/) | The earlier text-only prototype: farmer context, safety gate, conversation, structured outcomes (Gates 1 to 4 of the original plan). | Built, tested, kept as is |
| [`gate0/`](gate0/) | **Gate Zero**: End-to-end morning weather voice call orchestrator, SQLite persistence, 4-parameter weather ingestion, telephony retry engine, and real-time React operations dashboard. | Operational & Verified |
| [`final-product/`](final-product/) | The full Agrythm Connect, integrated with Trust AI. | Upcoming |

## How they fit together
Gate Zero is an end-to-end functional prototype. Its core talks to the outside world through agreed contracts and clean modular boundaries (farmer source, call ledger, weather, voice, telephony). In Gate Zero, farmer profiles sync live from Google Sheets, weather is grounded in 4 real-time Open-Meteo parameters, call histories persist in SQLite with automated retry state machines, and a field-ready dashboard provides telemetry and trigger controls. In the final product, the farmer source and call ledger connect to Trust AI, while the weather, voice, and telephony adapters carry over seamlessly. See [`gate0/docs/INTEGRATION.md`](gate0/docs/INTEGRATION.md).

## Quick start

### Gate Zero Orchestrator & Dashboard (Node.js & React)
```bash
cd gate0

# Install dependencies
npm install
npm --prefix server install
npm --prefix dashboard install

# Start the Backend Orchestrator & SQLite API (Port 8000)
npm run server

# In another terminal, start the Dashboard (Port 5173)
npm run dashboard:dev

# Run End-to-End verification test suite
npm run test:e2e
```

### Gate Zero Python CLI Runner
```bash
cd gate0
pip install -r requirements.txt
python -m pytest -q
python -m weathercall.cli --date 2026-11-05
```

### Earlier Prototype
```bash
cd Pilot
pip install -r requirements.txt
python -m pytest -q
python -m connect.cli --farmer 1
```

## Ground rules for the whole repository
- Farmer personal data and provider keys never go into GitHub. Use `.env` (ignored) and the `.env.example` files.
- The voice always says it is an AI, and only consented farmers are called.
- Strict agronomic boundary guardrails: weather voice agents decline chemical/pesticide advice and escalate non-weather inquiries immediately.
- Each area has its own `CLAUDE.md` with working rules. Read the one for the folder you are in.
- Decisions that matter are recorded as short notes (ADRs) in that area's `docs/`.
