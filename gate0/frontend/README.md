# Agrythm Connect — Voice Agent Telemetry & Operations Dashboard

> **Real-Time Voice Intelligence, Grounded 4-Parameter Weather Advisories, Multi-Lingual Telemetry & Telephony Orchestration for Gate Zero**  
> Built with **React 18+**, **Vite**, **Tailwind CSS**, **Node.js Express Orchestrator**, and **SQLite Persistence**.

---

## 🌾 Overview

**Agrythm Connect Dashboard** is a real-time agricultural voice telemetry and orchestration system designed for the Gate Zero voice agent. It provides end-to-end visibility into automated weather advisory phone calls dispatched to farmers across regional agricultural zones in **Kannada**, **Hindi**, and **English**.

The dashboard bridges live telephony execution records stored in the persistent SQLite database (`server/database/agrythm_connect.db`) with an interactive, field-first operator interface, supporting manual test dispatches, automated daily cron scheduling, real-time 4-parameter weather ingestion, and multi-lingual conversational dialogue inspection.

---

## ⚡ Key Architectural Features

### 1. End-to-End Orchestrator & Live SQLite Persistence
- **Persistent SQLite Telemetry Engine (`server/database/agrythm_connect.db`)**: Powered by native `node:sqlite` (`DatabaseSync`), storing complete call audit trails, attempt counts, transcripts, 4 weather parameters, retry schedules, and dispositions.
- **Pre-Call Guard & Idempotency Check**: Queries the SQLite database before initiating calls to verify whether the farmer was already successfully reached today (`isFarmerCalledToday`), preventing duplicate calls while allowing explicit "Start Demo" test overrides.
- **Automated Telephony 2-Retry Cycle**:
  - Handles telephony flags (`Unanswered`, `Busy`, `Failed`).
  - Automatically schedules retry attempts (`Attempt 1/3`, `Attempt 2/3`, status `Retrying`).
  - If retries exceed 2 attempts, marks call as `Failed: Fallback Sent` and records the complete attempt history in `call_attempts`.

### 2. 4-Parameter Grounded Meteorological Ingestion
- Ingests real-time weather from **Open-Meteo API** (`https://api.open-meteo.com/v1/forecast`) based on exact agricultural village coordinates:
  1. **Temperature (°C)** (`temperature_2m`)
  2. **Wind Speed (km/h)** (`wind_speed_10m`)
  3. **Rainfall / Precipitation Probability (%)** (`precipitation_probability`)
  4. **Relative Humidity (%)** (`relative_humidity_2m`)
- Automatically caches and grounds conversational responses strictly on these 4 parameters.

### 3. Multi-Lingual Dialogue & Strict Boundary Guardrails
- **Language-Aware Dialogue**:
  - Ingests farmer language preferences from Google Sheets and renders native dialogue scripts:
    - **Kannada**: `Dialogue Transcript (Kannada)` with native script and transliteration support.
    - **Hindi**: `Dialogue Transcript (Hindi)` with Devanagari script.
    - **English**: `Dialogue Transcript (English)`.
- **Weather Doubts Resolution**: Accurately resolves follow-up queries (e.g., rain timing, temperature, wind) strictly using the 4 fetched meteorological metrics.
- **Scheduled Callback Detection**: Intelligently extracts requested callback times from natural dialogue (e.g., *"Shaam ko 5 baje call karo"*, *"Call me after 2 PM"*) and populates `scheduled_callback_time` (e.g., `"Today, 5:00 PM"`).
- **Agronomic & Chemical Boundary Guardrail**: Strict safety boundary that immediately declines chemical or pesticide recommendations, politely directing farmers to local agricultural extension officers, and flags the call record as `status: Escalated`, `disposition: Non-Weather Inquiry`.

### 4. Real Data Google Sheets Synchronization
- Directly fetches farmer profiles from live Google Sheets CSV (`Sheet 1`), completely eliminating dummy or mock records.
- Automatically maps village coordinates (e.g., Humnabad: `17.7667, 77.2833`, Bhalki: `18.0441, 77.2185`) to ensure accurate hyper-local weather fetching.

### 5. Official Agrythm Brand Identity
- Integrated official Agrythm emblem logo across the desktop sidebar, mobile header, and browser favicon (`/agrythm-logo.png`).

---

## 🖥 Dashboard Views & Components

1. **Screen C01: Call History Table (`CallHistoryTable.jsx`)**:
   - Shows Call ID, timestamp, attempt number (`Attempt 1/3`, `Attempt 2/3`), farmer contact (masked for privacy), district, village, language badge (Kannada, Hindi, English), duration in seconds, and status badges (`Completed`, `Retrying`, `Failed`, `Escalated`).
   - Dedicated **Callback Slot** indicator displaying `scheduled_callback_time` when requested.
   - Clicking any call opens the comprehensive slide-over inspection drawer.

2. **Call Detail Drawer (`CallDetailDrawer.jsx`)**:
   - Displays the **4 Grounded Weather Parameters** used during the call.
   - Renders multi-turn conversational transcript bubbles with language headers (`Dialogue Transcript (Kannada)` / `(Hindi)`).
   - Displays scheduled callback reminders and agronomic escalation alerts.
   - Complete attempt audit trail detailing timestamp, status, and retry intervals.

3. **Operational Header Triggers (`Header.jsx`)**:
   - **"Start Demo" Trigger**: Executes an immediate batch test run across live farmer numbers with real-time state machine simulation.
   - **"Auto Dispatcher (9:00 AM)" Indicator & Toggle**: Displays and toggles the scheduled daily 9:00 AM IST dispatch cron job.

4. **Farmer Directory (`FarmerDirectory.jsx`)**:
   - Displays real farmer profiles fetched directly from Google Sheets.
   - Shows village, district, language preference, and masked phone numbers with quick filtering.

5. **Operational KPI Metrics (`KpiMetrics.jsx`)**:
   - 5-Card dynamic metrics: **Total Calls**, **Completed Calls**, **Farmers Reached**, **Retrying**, and **Escalations**.

---

## 🗂 Directory Structure

```text
gate0/
├── package.json                      # Workspace root scripts (start, backend, frontend)
├── backend/                          # Orchestrator & SQLite Telemetry Backend
│   ├── database/
│   │   ├── db.js                     # SQLite initialization, schema & queries (node:sqlite)
│   │   └── agrythm_connect.db        # Persistent SQLite database (git-ignored)
│   ├── routes/
│   │   ├── callsRouter.js            # /api/calls, /api/calls/trigger-demo, /api/calls/webhook
│   │   ├── farmersRouter.js          # /api/farmers (live Google Sheets sync)
│   │   ├── weatherRouter.js          # /api/weather (Open-Meteo 4-parameter proxy)
│   │   └── orchestratorRouter.js     # /api/orchestrator/status, /api/orchestrator/auto-dispatch
│   ├── services/
│   │   ├── conversationalEngine.js   # Intent classification, callback parsing & guardrails
│   │   ├── farmerService.js          # Live Google Sheets CSV ingestion & caching
│   │   ├── orchestrator.js           # Call lifecycle state machine, retries & cron scheduler
│   │   └── weatherService.js         # Open-Meteo 4-parameter weather service
│   ├── index.js                      # Express server entrypoint (Port 8000)
│   └── test_e2e.js                   # End-to-end integration & verification test suite
└── frontend/                         # React 18+ / Vite / Tailwind CSS Frontend
    ├── public/
    │   └── agrythm-logo.png          # Official Agrythm brand emblem
    ├── src/
    │   ├── assets/
    │   │   └── agrythm-logo.png      # Bundled brand asset
    │   ├── components/
    │   │   ├── CallDetailDrawer.jsx  # Slide-over inspection drawer & transcript bubbles
    │   │   ├── CallHistoryTable.jsx  # Telemetry table with retry badges & callback slots
    │   │   ├── FarmerDirectory.jsx   # Farmer directory from Google Sheets
    │   │   ├── Header.jsx            # Top bar with Start Demo & Auto Dispatcher controls
    │   │   ├── KpiMetrics.jsx        # 5-Card KPI metric summary
    │   │   ├── Sidebar.jsx           # Desktop navigation with Agrythm branding
    │   │   └── ...
    │   ├── hooks/
    │   │   ├── useVoiceAgentData.js  # Telemetry polling & call enrichment hook
    │   │   └── useDashboardData.js   # Orchestrator status & control hook
    │   └── utils/
    │       └── googleSheets.js       # Backend REST API client & Sheets utilities
    ├── index.html                    # Root HTML with Agrythm logo favicon
    └── vite.config.js                # Vite bundler configuration
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Node.js**: v20 or higher (v26+ recommended for built-in `node:sqlite`)
- **npm**: v10+

### 2. Start the Orchestrator Backend Server
From the `gate0/` directory:
```bash
# Start the Node.js Express server on port 8000
npm run backend
```
Or directly from `gate0/backend/`:
```bash
node index.js
```

The orchestrator logs:
```text
======================================================
Agrythm Connect - Orchestrator & SQLite API Server
Port: http://localhost:8000
Database: backend/database/agrythm_connect.db
Auto Dispatcher (9:00 AM IST): Active
======================================================
```

### 3. Start the Frontend Dashboard
In a separate terminal from `gate0/`:
```bash
# Start Vite development server
npm run frontend
```
Or from `gate0/frontend/`:
```bash
npm run dev
```

Open **[http://localhost:5173](http://localhost:5173)** in your browser.

### 4. Run the End-to-End Test Suite
Verify Google Sheets ingestion, 4-parameter weather fetching, multi-lingual dialogue handling, and SQLite persistence:
```bash
npm run test:e2e
```

---

## 📡 REST API Reference

### `GET /api/calls`
Retrieves all persistent call records joined with weather metrics, retry counts, and callback slots.

**Sample Response Item:**
```json
{
  "call_id": "CALL-1002-1793700000000",
  "farmer_id": "1002",
  "farmer_name": "Harshith",
  "phone_number": "6363713736",
  "location": "Bhalki, Bidar",
  "weather_temp": 29.2,
  "weather_windspeed": 14.5,
  "weather_rainfall": 16.0,
  "weather_humidity": 50.0,
  "status": "Completed",
  "disposition": "Callback Requested",
  "retry_count": 0,
  "scheduled_callback_time": "Today, 5:00 PM",
  "duration_seconds": 45,
  "transcript": [
    {"speaker": "Agent", "text": "ನಮಸ್ಕಾರ Harshith ಅವರೇ, ನಾನು ಅಗ್ರಿಥಮ್ ಕನೆಕ್ಟ್‌ನಿಂದ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ..."},
    {"speaker": "Farmer", "text": "ಈಗ ನಾನು ಹೊರಗಡೆ ಇದ್ದೇನೆ, ಸಂಜೆ 5 ಗಂಟೆಗೆ ಕಾಲ್ ಮಾಡಿ."},
    {"speaker": "Agent", "text": "ಖಂಡಿತ, ಸಂಜೆ 5:00 ಗಂಟೆಗೆ ನಿಮಗೆ ಮರಳಿ ಕರೆ ಮಾಡುತ್ತೇನೆ. ಧನ್ಯವಾದಗಳು."}
  ],
  "created_at": "2026-11-03 15:30:00"
}
```

### `POST /api/calls/trigger-demo`
Executes an immediate manual batch dispatch across registered farmers.

**Response:**
```json
{
  "success": true,
  "message": "Demo call batch initiated for 2 farmers",
  "dispatched_count": 2
}
```

### `GET /api/weather?lat=17.7667&lon=77.2833`
Returns the 4 real-time meteorological metrics for the given coordinates.

**Sample Response:**
```json
{
  "temperature": 28.0,
  "windSpeed": 14.7,
  "precipitationProbability": 22.0,
  "humidity": 58.0,
  "weatherSource": "Open-Meteo Live API"
}
```

### `GET /api/orchestrator/status`
Returns the operational status of the 9:00 AM IST auto-dispatcher cron job.

---

## 📄 License
Internal proprietary software for **Agrythm Connect — Weather Voice Agent System**. All rights reserved.
