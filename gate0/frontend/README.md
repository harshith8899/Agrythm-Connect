# Agrythm Connect: Operations Dashboard

React dashboard for the weather voice-call prototype (Gate Zero). It reads and controls the real Python backend in
`gate0/backend`: farmers, the day's calls, results from the Sarvam voice agent and callbacks.

Built with React 18, Vite and Tailwind CSS. No data is kept in the browser; it all comes from the API.

## What it shows

- **Call Logs (Screen C01):** one row per farmer per day with the 4 weather values that were sent, status
  (Completed, Retrying, Callback Scheduled, Not Confirmed, Unanswered, Failed, Skipped), attempts (for example 2 of 3),
  the next try time, duration and callback time. A rejected call and an unpicked one are shown the same way ("Not picked up or rejected"),
  because the phone network reports them the same.
  Filters for date, district, language (Hindi, Kannada, Telugu, English) and status.
- **Call detail panel:** the call result the agent recorded (summary, whether the farmer understood), the weather
  values, the attempt history and the dialogue transcript.
- **Farmer Directory:** the farmers in the database, with an **Import farmers (CSV)** button. Phone numbers are masked.
- **Weather Advisories:** the weather facts sent to each district (facts only, no farming advice).
- **System Status:** one page that shows whether the backend, database, weather API (Open-Meteo), Sarvam and the phone
  line (Exotel) are working, with the reason when one is not, plus Sarvam usage: an estimated amount in rupees, calls and billed minutes for today,
  7 days and 60 days, and per day. The amount is billed minutes times a per-minute rate you can change on the page (default
  ₹3.50, Sarvam pay-as-you-go, before GST). There is no credit balance: Sarvam has no API for it, so it is only on Sarvam's Settings, Billing page.
- **Header:** **Send now** places today's calls for every eligible farmer (it asks first when calls are real, and says
  "simulated" when no real calls are placed). **Auto Dispatcher** switches the daily 9:00 AM send on or off (off by default).

## Run it

Two terminals, from `gate0/`:

```bash
npm run backend      # Python API on http://127.0.0.1:8000
npm run frontend     # dashboard on http://localhost:5173 (proxies /api to the backend)
```

The backend reads `gate0/.env`. With `GATE0_TELEPHONY=sarvam_agent` and the Sarvam settings complete it places real calls;
otherwise it runs in **simulated** mode and the header says so. See `gate0/docs/SARVAM_SETUP.md`.

For a hosted dashboard, build with the API's address and allow the dashboard's address on the backend:

```bash
VITE_API_URL=https://your-api.example.com npm run frontend:build
GATE0_CORS_ORIGINS=https://your-dashboard.example.com python -m weathercall.server
```

## The API the dashboard uses

| Route | What it does |
|---|---|
| `GET /api/calls`, `GET /api/calls/<id>` | Call records (weather, status, attempts, transcript, summary, callback) |
| `GET /api/farmers`, `POST /api/farmers/import` | Farmers (masked phones); import a CSV (same Farmer ID updates) |
| `POST /api/calls/send-now` | Send today's calls now (returns at once, results appear as calls finish) |
| `GET /api/callbacks` | Callbacks waiting, placed, unanswered or missed |
| `GET /api/orchestrator/status`, `POST /api/orchestrator/auto-dispatch` | Mode (real or simulated), last send, daily auto-send switch |
| `GET /api/weather?lat=&lon=` | Today's weather for a place |
| `GET /api/system/checks` | Backend, database, weather API, Sarvam and phone line: ok, fail or not set up |
| `POST /api/farmers/<id>/call` | Place a call now for one farmer: the day's first call, or the next retry |
| `POST /api/farmers`, `PUT /api/farmers/<id>` | Add one farmer by hand; edit a farmer (name, phone, language, place, consent, active) |
| `GET /api/alerts` | Things the team must act on (stop requests, failed calls, skipped runs); shown on System Status |
| `GET /api/usage`, `POST /api/usage` | Calls, billed minutes and the estimated amount from Sarvam's call records; POST saves the per-minute rate |

Phone numbers are masked in every response. There is no login yet; it must be added before the dashboard is exposed.

## Layout

```text
gate0/
├── backend/        Python backend: engine, Sarvam adapters, service.py, server.py (the API), tests
└── frontend/       this dashboard
    └── src/
        ├── components/   Header, KpiMetrics, CallHistoryTable, CallDetailDrawer, FarmerDirectory, WeatherAlertsView ...
        ├── hooks/        useVoiceAgentData (polling and call enrichment), useDashboardData
        └── utils/        api.js (the API client), constants.js (API address), analytics and transcript helpers
```

`gate0/backend/index.js`, `routes/`, `services/` and `database/` are the earlier Node simulation. They are not used by the
dashboard any more (`npm run backend:node-legacy` still starts them) and can be removed once the team agrees.
