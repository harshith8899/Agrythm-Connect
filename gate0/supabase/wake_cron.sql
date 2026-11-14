-- The timer: every minute, ask backend_needed() and, if it says yes, call the backend's POST /api/tick.
--
-- Needs (done once, see docs/TRIGGER.md): the extensions pg_cron and pg_net, and two Vault secrets:
--   agrythm_backend_url   the Render address, e.g. https://agrythm-gate0-api.onrender.com
--   agrythm_api_token     the same API token the backend uses (X-API-Token)
-- Without the secrets the timer only writes "not configured" to wake_log; it never fails and never calls anything.

create or replace function agrythm.wake_backend()
returns text
language plpgsql
security definer
set search_path = agrythm, extensions, vault, net, pg_temp
as $fn$
declare
  why   text := agrythm.backend_needed();
  url   text;
  token text;
  req   bigint;
begin
  if why is null then
    return null;
  end if;
  select decrypted_secret into url   from vault.decrypted_secrets where name = 'agrythm_backend_url';
  select decrypted_secret into token from vault.decrypted_secrets where name = 'agrythm_api_token';
  if url is null or token is null then
    insert into agrythm.wake_log(reason, note) values (why, 'not configured: add the Vault secrets');
    return 'not configured';
  end if;
  select net.http_post(
           url := rtrim(url, '/') || '/api/tick',
           headers := jsonb_build_object('Content-Type', 'application/json', 'X-API-Token', token),
           body := '{}'::jsonb,
           timeout_milliseconds := 60000) into req;
  insert into agrythm.wake_log(reason, request_id) values (why, req);
  delete from agrythm.wake_log where at < now() - interval '7 days';
  return why;
end
$fn$;

revoke all on function agrythm.wake_backend() from public;

select cron.unschedule('agrythm-wake-backend') where exists (select 1 from cron.job where jobname = 'agrythm-wake-backend');
select cron.schedule('agrythm-wake-backend', '* * * * *', $$select agrythm.wake_backend()$$);
