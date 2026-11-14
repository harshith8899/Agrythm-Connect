-- Paste-ready copy of wake_rules.sql for the agrythm schema (generated: __SCHEMA__ replaced by agrythm). Run it once in the Supabase SQL editor.
-- When must the backend be awake? (Supabase, Postgres)
--
-- A free Render service sleeps after about 15 minutes without a visit. This function reads the same tables the backend
-- writes and answers with the reason the backend is needed within the next 3 minutes, or NULL when it is not. A timer
-- (wake_cron.sql) asks it every minute and, when it answers, calls the backend. The backend then decides what to do
-- exactly as it always does: a call is only placed when it is really due, so waking it early or twice changes nothing.
--
-- agrythm is the schema that holds the tables (agrythm). Times are India time; the backend stores them as ISO text
-- with the +05:30 offset, which casts to timestamptz.

create table if not exists agrythm.wake_log (
  id bigserial primary key,
  at timestamptz not null default now(),
  reason text not null,
  request_id bigint,
  note text
);
alter table agrythm.wake_log enable row level security;

create or replace function agrythm.backend_needed(at timestamptz default now())
returns text
language plpgsql
stable
security definer
set search_path = agrythm, pg_temp
as $fn$
declare
  ist     timestamp := at at time zone 'Asia/Kolkata';
  today   text      := to_char(ist, 'YYYY-MM-DD');
  lead    interval  := interval '3 minutes';      -- wake this long before the due time (a cold start takes about a minute)
  enabled boolean   := coalesce((select value from dash_settings where key = 'auto_dispatch'), 'off') = 'on';
  last_day text     := coalesce((select value from dash_settings where key = 'last_auto_run_date'), '');
  last_run text     := (select value from dash_settings where key = 'last_auto_run');
begin
  -- 1. a retry is due, or about to be (a stale pending one keeps the backend called until it marks it missed)
  if exists (select 1 from dash_retries where status in ('pending', 'calling') and due_at::timestamptz <= at + lead) then
    return 'retry due';
  end if;

  -- 2. a callback the farmer asked for is due, or about to be
  if exists (select 1 from dash_callbacks where status in ('pending', 'calling') and due_at::timestamptz <= at + lead) then
    return 'callback due';
  end if;

  -- 3. the daily send (only when auto-send is on), inside the calling window; the backend starts it at 09:00. The timer starts
  --    waking it at 08:47 and then pings it every minute, so the free plan (which sleeps after about 15 idle minutes) stays up.
  if enabled and ist::time >= time '08:47' and ist::time <= time '22:00' then
    if last_day <> today then
      return 'daily send due';
    end if;
    -- 4. the send is under way: keep the backend awake until every active, consenting farmer has a result for today
    if last_run is not null and last_run::timestamptz > at - interval '2 hours'
       and exists (select 1 from dash_farmers f
                   where f.active = 1 and f.consent = 1
                     and not exists (select 1 from dash_results r where r.farmer_id = f.farmer_id and r.call_date = today)) then
      return 'daily send running';
    end if;
  end if;

  return null;
end
$fn$;

revoke all on function agrythm.backend_needed(timestamptz) from public;

-- the timer runs as postgres: let it add its own function, read the rule and write the log
grant usage, create on schema agrythm to postgres;
grant execute on function agrythm.backend_needed(timestamptz) to postgres;
grant select, insert, delete on agrythm.wake_log to postgres;
grant usage, select on sequence agrythm.wake_log_id_seq to postgres;
