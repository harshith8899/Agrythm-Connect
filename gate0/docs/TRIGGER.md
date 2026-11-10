# The wake-up timer (free Render plan)

A free Render service sleeps after about 15 minutes without a visit, and the daily send, retries and callbacks run inside it.
So a small timer in Supabase wakes it about 3 minutes before anything is due. Nothing in the calling logic changes: the backend
still decides, as always, what is due and places a call only at its time.

```
Supabase (every minute)                              Render (free, sleeps when idle)
  cron job agrythm-wake-backend                        POST /api/tick  ->  one pass of "what is due"
    -> agrythm.backend_needed()  "is something due       (retries, callbacks, the 9:00 send), at most
       within 3 minutes?"                                one pass at a time
    -> yes: pg_net calls POST /api/tick  ------------->  and the 30-second loop keeps running while awake
    -> no:  does nothing
```

## When the timer wakes the backend (`gate0/supabase/wake_rules.sql`)
| Reason in the log | Condition |
|---|---|
| `retry due` | a retry is pending and due within 3 minutes (or already due) |
| `callback due` | a callback the farmer asked for is pending and due within 3 minutes (or already due) |
| `daily send due` | auto-send is on, it is between 08:57 and 22:00, and today's send has not started |
| `daily send running` | the send started in the last 2 hours and an active, consenting farmer still has no result today |

Everything else is quiet, so the service sleeps. A wake-up that is early, repeated or late changes nothing: `POST /api/tick`
runs one pass at a time (a second one is ignored), and a retry or callback is only placed when its time has come, with the same
30-minute grace as before. A cold start takes about a minute, so a call is at most a few minutes late.

## One-time setup (after the Render service is live)
The extensions, the rule, the log and the timer are already installed in the Mumbai project. Two secrets are missing, and only you
should type them. In Supabase, SQL Editor, run (with your real values; the address has no trailing slash):

```sql
select vault.create_secret('https://YOUR-SERVICE.onrender.com', 'agrythm_backend_url');
select vault.create_secret('YOUR_API_TOKEN', 'agrythm_api_token');
```

The token is the same `GATE0_API_TOKEN` you set on Render. Until both secrets exist the timer only writes `not configured` to the
log and calls nothing. To change a secret later, delete it in Vault (Project settings, Vault) and create it again.

## Check that it works
```sql
-- what the timer decided (newest first); request_id is the web call it made
select at at time zone 'Asia/Kolkata' as india_time, reason, request_id, note from agrythm.wake_log order by id desc limit 20;

-- what Render answered to those calls (202 means "started")
select id, status_code, created, left(content, 80) as answer, error_msg from net._http_response order by created desc limit 10;

-- is the timer running
select jobname, schedule, active from cron.job where jobname = 'agrythm-wake-backend';
select status, start_time, return_message from cron.job_run_details order by start_time desc limit 5;
```
A good first test: add a callback or retry due in about 5 minutes (or ask a test farmer to be called in 5 minutes), then watch
`wake_log` get a `callback due` row 3 minutes before, and `_http_response` show `202`.

## Switching it off or changing it
- Pause: `select cron.alter_job((select jobid from cron.job where jobname = 'agrythm-wake-backend'), active := false);`
- Resume: the same with `active := true`.
- Always-on Render (Starter plan): change `plan` in `render.yaml`. The timer can stay; the extra calls are harmless.

## Limits
- **Cold start:** about a minute. Calls may be 2 to 3 minutes late; that is accepted.
- **A long daily send:** each call takes a minute or two and the sends run one after another. For 10 to 15 farmers the timer keeps
  the backend awake the whole time (`daily send running`). For hundreds, move to the Starter plan.
- **Restarts:** Render may restart a free service at any time. A restart during a call can lose that call's result, and the
  backend would retry according to the usual rules.
- **If Supabase or the timer stops,** nothing wakes the backend. Check `wake_log` now and then; an alert for this is a good next step.
- **Only one backend on the same data.** Do not run your laptop's backend on the same Supabase data while Render is live, or the
  daily send may run from both.
