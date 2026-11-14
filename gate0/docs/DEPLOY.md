# Hosting and CI/CD

The API runs on Render, the dashboard on Cloudflare Pages, and GitHub Actions tests every change before either deploys.

```
GitHub (main) ── CI: Pilot tests, Gate Zero tests, frontend lint + build
      │                         │ all green
      │                         ├── Render deploys the API        (autoDeployTrigger: checksPass in render.yaml)
      │                         └── Cloudflare Pages deploys the dashboard (deploy-frontend job)
Browser ── Cloudflare Access (login) ── Pages ── /api/* Pages Function ── (adds the token) ── Render API ── Sarvam
```

The browser never sees the API token. The Pages Function (`gate0/frontend/functions/api/[[path]].js`) forwards `/api/*`
to Render and adds the token on the server side. Cloudflare Access must sit in front of the Pages site, otherwise anyone
who finds the address could read farmer data and press "Send now" (real calls cost credits).

## Things to know before you start
- **One API instance only.** The scheduler (daily send, retries, callbacks) runs inside the API process. Two instances, or
  this API plus your laptop with auto-send on, would call every farmer twice. Keep auto-send off on your laptop.
- **The database is Supabase** (Postgres, Mumbai). Set it up first with `docs/SUPABASE.md`; the API only needs the
  `GATE0_DATABASE_URL` address, no disk. Render has no Mumbai region, so the API runs in Singapore, the nearest one.
- **Free plan plus a wake-up timer.** The service sleeps when idle and a timer in Supabase wakes it before anything is due; see
  `docs/TRIGGER.md` (one-time setup after the first deploy). For many farmers, switch `plan` to `starter` in `render.yaml`
  (about 7 USD a month, always on).
- **Costs:** Render free plan 0 (Starter about 7 USD a month if you switch). Cloudflare Pages and Access (up to 50 users) and the Supabase free plan
  cost nothing. Sarvam (voice agent and its telephony number) is billed separately.
- **Farmers are real data and are not in git.** Copy your local data into Supabase with
  `python -m weathercall.migrate_db` (see `docs/SUPABASE.md`), or import the sheet again in the hosted dashboard.

## 1. Render (API)
1. Render dashboard, New, Blueprint, pick this repository. It reads `render.yaml` and creates `agrythm-gate0-api`.
2. Fill the values marked as secrets: `GATE0_DATABASE_URL` (the Supabase Session pooler address), `GATE0_API_TOKEN`, `SARVAM_AGENT_API_KEY`, `SARVAM_ORG_ID`,
   `SARVAM_WORKSPACE_ID`, `SARVAM_APP_ID`, `SARVAM_CONNECTION_ID`, `SARVAM_AGENT_PHONE` (same values as your local
   `gate0/.env`). Make the token with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and keep a copy for
   step 2 below. `SARVAM_APP_VERSION` is 10 in `render.yaml`; change it there when a new agent version is committed.
3. Deploy. Open `https://<service>.onrender.com/api/health`: it must answer `{"status": "ok"}`. Any other `/api` address
   answers 401 without the token, which is correct.
4. The API refuses to start on a public address without `GATE0_API_TOKEN`; a failed start usually means that is missing.
   Weather: add `WEATHERAPI_KEY` (the free key from weatherapi.com, as a secret) under Environment and redeploy; when it is set,
   WeatherAPI.com is the weather source (Open-Meteo's free service throttles shared hosting addresses with HTTP 429). Weather is
   fetched only when a call is made, once per place and day, and the System Status tab never asks the weather service.
5. Render, Settings, Build and Deploy: Auto-Deploy should show "After CI checks pass".

## 2. Cloudflare (the dashboard)
Cloudflare's current "Set up your application" screen creates a **Worker with static assets**. `gate0/frontend/wrangler.jsonc` and
`gate0/frontend/worker/index.js` are made for it: the Worker serves the built dashboard and forwards `/api/*` to Render with the
API token added on the server side, so the token never reaches the browser. (The older Pages setup, with
`functions/api/[[path]].js`, does the same job and still works if you create a Pages project instead.)

1. Cloudflare dashboard, Workers & Pages, Create, import the GitHub repository `Agrythm-Connect`.
2. On "Set up your application":
   - Project name `agrythm-connect` (it must match `name` in `wrangler.jsonc`).
   - Build command `npm run build`. Deploy command `npx wrangler deploy` (the default).
   - Tick **Protect with Cloudflare Access** (see step 4).
   - Open **Advanced settings**: Root directory **`gate0/frontend`**; leave the API token on "create new token"; under variables add
     the build variable `NODE_VERSION` = `22`.
   - Leave **Enable preview builds** off for now.
   - Click **Deploy**. The first build takes a couple of minutes. The address looks like `agrythm-connect.<your-name>.workers.dev`.
3. Give the Worker its two settings: open the Worker, Settings, **Variables and Secrets**, and add both as type **Secret**:
   `BACKEND_URL` = the Render address (no trailing slash) and `API_TOKEN` = the same token as `GATE0_API_TOKEN` on Render. Save and
   deploy. (These are runtime settings. The variables under "Advanced settings" on the setup screen are only for the build.)
4. **Protect the site (required).** Anyone who can open the site could otherwise read farmer data and press Send now. The tick box
   in step 2 puts Cloudflare Access in front of the address. Then Zero Trust, Access, Applications, open that application, and edit
   its policy: Action **Allow**, Include **Emails**, the team's addresses. The first time, Zero Trust asks for a team name and the
   Free plan (up to 50 users).
5. The dashboard calls `/api` on its own address, so no `VITE_API_URL` is needed in production.

If something is wrong: `API proxy is not configured` (503) means `BACKEND_URL` or `API_TOKEN` is missing; `unauthorized` (401) means
the token differs from Render's; `Backend not reachable` (502) means Render is not answering (it may still be waking up).

## 3. GitHub
Settings, Branches, add a rule for `main`: require a pull request and require the status checks `pilot-tests`,
`gate0-backend-tests` and `gate0-frontend`. After that, only tested code reaches `main`, and only `main` deploys.
(Optional: to deploy the dashboard from GitHub Actions instead of Cloudflare's Git connection, add the secrets
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` and the variable `DEPLOY_FRONTEND` = `true`, and do not use the Git connection.)

## What happens on each change
| Event | What runs |
|---|---|
| Pull request | Pilot tests, Gate Zero tests, frontend lint and build |
| Merge to `main` | the same, then Cloudflare Pages deploys the dashboard; Render deploys the API once the checks pass |

## Rollback
- API: Render, the service, Events, pick the earlier deploy, Rollback.
- Dashboard: Cloudflare Pages, Deployments, pick the earlier one, Rollback to this deployment.
- Agent behaviour is separate: calls use the Sarvam agent version in `SARVAM_APP_VERSION`, so changing it back is a
  setting, not a deploy.

## Checking it works
1. Open the Pages address, sign in through Access, open System Status: Backend, Database, Weather and Sarvam should be OK.
2. Import a test sheet with one team member's number, leave auto-send off, press "Send now" once, and confirm the call and
   the result row.
3. Only then switch the daily 9:00 auto-send on.
