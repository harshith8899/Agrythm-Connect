# Gate Zero: Morning Weather Call & Voice Orchestrator

A standalone, end-to-end voice telephony orchestrator and real-time operations dashboard. Each morning, automated voice calls go to consented farmers across regional agricultural zones, delivering real-time weather advisories in **Kannada**, **Hindi**, or **English**, stating clearly that the caller is an AI.

---

## 🌾 What Gate Zero Does

1. **Farmer Data Ingestion:** Synchronizes live farmer profiles directly from Google Sheets (`Sheet 1`), extracting `farmer_id`, `name`, `phone`, `village`, `district`, and `preferred_language`.
2. **Pre-Call Guard & Idempotency:** Queries the SQLite database (`server/database/agrythm_connect.db`) to verify if a farmer was already successfully reached on today's calendar date, skipping duplicates unless manually triggered.
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

### Option A: Node.js Orchestrator & React Dashboard (Recommended)

```bash
# 1. Install workspace dependencies
cd gate0
npm install
npm --prefix server install
npm --prefix dashboard install

# 2. Start the Backend Orchestrator & SQLite API (Port 8000)
npm run server

# 3. In a separate terminal, start the Dashboard (Port 5173)
npm run dashboard:dev

# 4. Run the full E2E verification test suite
npm run test:e2e
```
Open **[http://localhost:5173](http://localhost:5173)** to access the Agrythm Connect Dashboard.

---

### Option B: Python Core Contracts & CLI Runner

```bash
cd gate0
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

- `server/` Node.js Express Orchestrator and SQLite persistence API
  - `database/db.js` SQLite schema, queries, and attempt audit logs
  - `services/orchestrator.js` State machine, 2-retry cycle, and 9:00 AM IST cron
  - `services/weatherService.js` Open-Meteo 4-parameter weather client
  - `services/farmerService.js` Live Google Sheets farmer profiles ingestion
  - `services/conversationalEngine.js` Kannada/Hindi/English intent & guardrail parser
  - `test_e2e.js` Automated integration and verification test suite
- `dashboard/` React 18 / Vite / Tailwind CSS Telemetry & Operations Dashboard
  - `src/components/CallHistoryTable.jsx` Status badges, attempt counters, and callback slots
  - `src/components/CallDetailDrawer.jsx` 4-Weather parameter grounding and native dialogues
  - `src/components/Header.jsx` "Start Demo" button and Auto-Dispatcher indicator
  - `src/components/Sidebar.jsx` Navigation with official Agrythm branding
- `weathercall/` Python core contracts, ports, and standalone CLI runner
- `docs/` Integration guidelines, decisions, and provider configurations

---

## 🛡 Safety and Guardrails

- **Explicit AI Disclosure:** Every call begins by stating clearly that the caller is an automated AI weather reporter.
- **Strict Boundary Guardrail:** The voice agent declines any non-weather or agronomic/chemical inquiries, escalating them immediately.
- **Farmer Consent:** Calls are strictly placed to registered farmers with recorded consent.
- **Data Protection:** Farmer phone numbers are masked on all operational dashboard views.
