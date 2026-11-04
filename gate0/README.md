# Gate Zero: Morning Weather Call & Voice Orchestrator

A standalone, end-to-end voice telephony orchestrator and real-time operations dashboard. Each morning, automated voice calls go to consented farmers across regional agricultural zones, delivering real-time weather advisories in **Kannada**, **Hindi**, or **English**, stating clearly that the caller is an AI.

---

## 🌾 What Gate Zero Does

1. **Farmer Data Ingestion:** Synchronizes live farmer profiles directly from Google Sheets (`Sheet 1`), extracting `farmer_id`, `name`, `phone`, `village`, `district`, and `preferred_language`.
2. **Pre-Call Guard & Idempotency:** Queries the SQLite database (`backend/database/agrythm_connect.db`) to verify if a farmer was already successfully reached on today's calendar date, skipping duplicates unless manually triggered.
3. **4-Parameter Grounded Weather Ingestion:** Ingests live meteorological data from **Open-Meteo** based on the farmer's coordinates:
   - **Temperature (°C)**
   - **Wind Speed (km/h)**
   - **Rainfall / Precipitation Probability (%)**
   - **Relative Humidity (%)**
4. **Multi-Lingual Conversational Engine:**
   - **Native Multi-Lingual Transcripts:** Formulates natural speech and dialogue in **Kannada**, **Hindi**, and **English**.
   - **Weather Doubts Resolution:** Answers follow-up weather questions strictly grounded on the 4 fetched meteorological metrics.
   - **Callback Slot Extraction:** Extracts requested callback times (e.g., *"Shaam ko 5 baje call karo"*, *"ಸಂಜೆ 5 ಗಂಟೆಗೆ ಕಾಲ್ ಮಾಡಿ"*) and schedules the slot (`scheduled_callback_time: "Today, 5:00 PM"`).
   - **Agronomic Boundary Guardrail:** Strictly refuses pesticide/chemical or seed advice, politely referring farmers to agricultural extension officers, and flags `status: Escalated`, `disposition: Non-Weather Inquiry`.
5. **Telephony 2-Retry Engine:** Handles `Unanswered`, `Busy`, or `Failed` calls by scheduling up to 2 retry attempts (`Attempt 1/3`, `Attempt 2/3`, status `Retrying`). If all attempts fail, marks the record as `Failed: Fallback Sent`.
6. **Real-Time Telemetry Dashboard:** Full React/Vite/Tailwind operator interface featuring live call logs, 5-card dynamic KPIs, audio inspection drawer with 4 weather badges, "Start Demo" test trigger, and daily 9:00 AM IST Auto-Dispatcher toggle.

---

## ⚡ Quick Start

### 1. Unified Node.js & React Dashboard Runner

```bash
cd gate0

# 1. Install root, backend, and frontend dependencies
npm install
npm --prefix backend install
npm --prefix frontend install

# 2. Start the Backend Orchestrator & SQLite API (Port 8000)
npm run backend

# 3. In a separate terminal, start the Frontend Dashboard (Port 5173)
npm run frontend

# 4. Run the full E2E verification test suite
npm run test:e2e
```
Open **[http://localhost:5173](http://localhost:5173)** to access the Agrythm Connect Dashboard.

---

### 2. Python Core Contracts & CLI Runner

```bash
cd gate0/backend
pip install -r requirements.txt
python -m pytest -q
python -m weathercall.cli --date 2026-11-05
```

---

## 🏛 Architecture & Contracts

```text
 ┌────────────────────────────────────────────────────────┐
 │            Operator Dashboard / Triggers               │
 │    ("Start Demo" Button  •  9:00 AM Auto-Dispatcher)   │
 └───────────────────────────┬────────────────────────────┘
                             │ REST / Webhooks
                             v
 ┌────────────────────────────────────────────────────────┐
 │           Node.js Express Call Orchestrator            │
 │                   (Port: 8000)                         │
 └──────┬────────────────────┬────────────────────┬───────┘
        │                    │                    │
        v                    v                    v
 ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
 │Google Sheets│      │ Open-Meteo  │      │   SQLite    │
 │Farmer Ingest│      │  4-Weather  │      │ Persistence │
 └─────────────┘      └─────────────┘      └─────────────┘
```

The system core talks to external services via clean modular boundaries:
- **Farmer Source:** Live Google Sheets CSV synchronization with coordinate lookups.
- **Weather Service:** Open-Meteo 4-parameter real-time forecasting.
- **Conversational Engine:** Intent parser, callback time extractor, and non-weather boundary guardrail.
- **Call Ledger:** Persistent SQLite database tracking every call and attempt audit trail.

---

## 🗂 Directory Layout

```text
gate0/
├── backend/                          # ALL BACKEND SYSTEMS
│   ├── database/                     # SQLite persistence layer (node:sqlite)
│   │   ├── db.js                     # Tables: calls, call_attempts, farmers
│   │   └── agrythm_connect.db        # Persistent SQLite database (git-ignored)
│   ├── routes/                       # Express REST API routes
│   │   ├── callsRouter.js            # /api/calls, /api/calls/trigger-demo, /api/calls/webhook
│   │   ├── farmersRouter.js          # /api/farmers (live Google Sheets sync)
│   │   ├── weatherRouter.js          # /api/weather (Open-Meteo proxy)
│   │   └── orchestratorRouter.js     # /api/orchestrator/status & auto-dispatch
│   ├── services/                     # Business logic services
│   │   ├── conversationalEngine.js   # Multi-lingual dialogue, callback parsing, guardrails
│   │   ├── farmerService.js          # Google Sheets CSV ingestion & caching
│   │   ├── orchestrator.js           # 2-retry cycle, batch runner, 9:00 AM cron
│   │   └── weatherService.js         # 4-parameter Open-Meteo weather client
│   ├── weathercall/                  # Python Voice Telephony & Sarvam Agent Engine
│   │   ├── adapters/                 # Sarvam Agent, Exotel, Open-Meteo, Local, Mock
│   │   ├── campaign.py               # Sarvam campaign scheduling & sync
│   │   ├── cli.py                    # Standalone CLI morning call runner
│   │   ├── config.py                 # Environment settings loader
│   │   ├── contracts.py              # Interface contracts and schemas
│   │   ├── engine.py                 # Core call state machine and idempotency
│   │   ├── ports.py                  # Port specifications
│   │   ├── schedule.py               # Windows Task Scheduler automation
│   │   ├── script.py                 # Spoken message templates & weather_variables
│   │   ├── server.py                 # Standalone Python telemetry server
│   │   └── weather_check.py          # Pre-flight weather verification script
│   ├── tests/                        # Automated backend test suites
│   │   ├── test_e2e.js               # Node.js end-to-end integration test
│   │   ├── test_campaign.py          # Python campaign tests
│   │   ├── test_engine.py            # Python core engine tests
│   │   ├── test_sarvam_agent.py      # Python Sarvam agent tests
│   │   ├── test_script_and_wiring.py # Python script templates tests
│   │   ├── test_sheet_sarvam_schedule.py # Python sheet & schedule tests
│   │   └── test_weather.py           # Python weather tests
│   ├── index.js                      # Express server entry point (Port 8000)
│   ├── package.json                  # Backend Node.js dependencies & scripts
│   ├── package-lock.json             # Node.js lockfile
│   ├── pyproject.toml                # Python package & pytest configuration
│   └── requirements.txt              # Python dependencies
│
├── frontend/                         # ALL FRONTEND WORK (React 18+ / Vite / Tailwind)
│   ├── public/                       # Static public assets (brand logo, icons)
│   ├── src/
│   │   ├── assets/                   # Bundled brand assets (agrythm-logo.png)
│   │   ├── components/               # React UI components & views
│   │   │   ├── CallDetailDrawer.jsx  # Slide-over call inspection & transcripts
│   │   │   ├── CallHistoryTable.jsx  # Real-time call history table
│   │   │   ├── FarmerDirectory.jsx   # Farmer directory from Google Sheets
│   │   │   ├── Header.jsx            # Top controls ("Start Demo", Auto Dispatcher)
│   │   │   ├── KpiMetrics.jsx        # 5-card operational metrics
│   │   │   ├── Sidebar.jsx           # Sidebar navigation with Agrythm branding
│   │   │   └── ...
│   │   ├── hooks/                    # Data hooks (useVoiceAgentData, useDashboardData)
│   │   ├── utils/                    # Client utilities (googleSheets.js, constants.js)
│   │   ├── App.jsx                   # Main layout shell & tab router
│   │   ├── index.css                 # Tailwind stylesheet
│   │   └── main.jsx                  # React DOM root entry point
│   ├── index.html                    # Root HTML file
│   ├── package.json                  # Frontend dependencies & Vite scripts
│   ├── package-lock.json             # Frontend lockfile
│   ├── postcss.config.js             # PostCSS plugins
│   ├── tailwind.config.js            # Tailwind color & font theme
│   └── vite.config.js                # Vite dev server & API proxy config
│
├── docs/                             # SHARED DOCUMENTATION & ADRs
│   ├── DECISIONS.md                  # Chronological project decision log
│   ├── INTEGRATION.md                # Platform port & contract integration guide
│   └── SARVAM_SETUP.md               # Sarvam AI voice & Exotel telephony setup
│
├── .env.example                      # Root environment variables template
├── CLAUDE.md                         # Project development ground rules
├── farmers.example.csv               # Sample farmer profile CSV
├── package.json                      # Root workspace scripts (npm run backend, npm run frontend)
└── README.md                         # Comprehensive project documentation

---

## 🛡 Safety and Guardrails

- **Explicit AI Disclosure:** Every call begins by stating clearly that the caller is an automated AI weather reporter.
- **Strict Boundary Guardrail:** The voice agent declines any non-weather or agronomic/chemical inquiries, escalating them immediately.
- **Farmer Consent:** Calls are strictly placed to registered farmers with recorded consent.
- **Data Protection:** Farmer phone numbers are masked on all operational dashboard views.
