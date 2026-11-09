# Supabase (Postgres) setup

The API stores farmers, call results, retries, callbacks, alerts and saved weather in a database. By default that is the
SQLite file `backend/weathercall.db`. Set `GATE0_DATABASE_URL` to a Supabase address and the same code runs on Postgres.
Nothing else changes: with the variable empty everything still uses SQLite (local work and the tests).

## 1. Create the project (you)
1. supabase.com, New project. Name `agrythm-connect`. Region: the closest to your users, for example Mumbai (ap-south-1).
2. Set a strong database password and keep it in a password manager. You cannot read it again later.
3. Project, Connect, **Session pooler**. Copy the URI. It looks like
   `postgresql://postgres.<project>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   Use the **session pooler**, not the direct address: the direct address is IPv6 only and fails on Render and many home
   networks. Replace `[YOUR-PASSWORD]` with the password; if it has special characters, percent-encode them (`@` is `%40`).
4. Put it in `gate0/.env` as `GATE0_DATABASE_URL=...`. That file is not in git. Do not paste the address in chat, in an
   issue or in a commit: it holds the password.

## 2. Check it works (no data is touched)
```bash
cd gate0/backend
python -m pip install "psycopg[binary]"
python -m weathercall.migrate_db --from weathercall.db --to "$GATE0_DATABASE_URL" --dry-run
```
The dry run only counts the rows in the SQLite file. To prove Postgres itself works, run the whole test suite on it: every
test uses its own throwaway schema (`t_...`), which is dropped at the end, and your real tables are never touched:
```bash
GATE0_TEST_DATABASE_URL="$GATE0_DATABASE_URL" python -m pytest -q
```
(In PowerShell: `$env:GATE0_TEST_DATABASE_URL=$env:GATE0_DATABASE_URL; python -m pytest -q`.)

## 3. Copy the existing data
```bash
python -m weathercall.migrate_db --from weathercall.db --to "$GATE0_DATABASE_URL"
```
It can be repeated: rows already there are left alone. It prints only counts, never farmer data.

## 4. Run on Supabase
Start the backend as usual (`npm run backend`). The first line says `database: Postgres (Supabase)`, and System Status shows
the database check as "Postgres (Supabase)". Open the dashboard and confirm your farmers and call history are there.
To go back to SQLite, empty `GATE0_DATABASE_URL`.

## How it is kept safe
- The tables are in their own schema, `agrythm` (`GATE0_DB_SCHEMA`), not in `public`. Supabase serves `public` through its
  REST API to anyone holding the public (anon) key; a separate schema is not served.
- Row level security is switched on for every table as well, with no policies, so the public keys read nothing even if a
  table were exposed later. The API connects with the database password, which is not affected by those rules.
- Keep the database password and the connection string out of git, logs and chat. Rotate the password in Supabase
  (Project settings, Database) if it ever leaks, then update `GATE0_DATABASE_URL`.
- Farmer phone numbers are stored in full because a call needs them. Supabase encrypts data at rest; the API never returns a
  number unmasked.

## Notes
- Each statement is its own transaction (autocommit), so one failed statement never blocks the next.
- Times are stored as text in India time, as before, so no timezone setting is needed.
- Hosting the API (Render and so on) needs only `GATE0_DATABASE_URL` set there; no disk is needed any more.
