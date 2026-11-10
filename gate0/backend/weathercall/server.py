"""HTTP API for the React dashboard. Same routes the dashboard already calls, served from the real backend service.

    cd gate0/backend
    python -m weathercall.server            listens on http://127.0.0.1:8000  (PORT / GATE0_API_HOST to change)

    GET  /api/health                         GET  /api/orchestrator/status
    GET  /api/calls   GET /api/calls/<id>    POST /api/orchestrator/auto-dispatch   {"enabled": true|false}
    GET  /api/farmers                        POST /api/orchestrator/run-now         send today's calls now
    POST /api/tick             wake-up for an outside timer: runs one pass of what is due (retries, callbacks, the daily send)
    POST /api/farmers/<id>/call  place a call now for one farmer; body {"mode": "retry"} follows the retry rules (default),
                                 {"mode": "test"} is a test call kept as its own row, outside the retry rules
    POST /api/farmers          add one farmer;  PUT/PATCH /api/farmers/<id>  edit one (also active and consent)
    POST /api/farmers/import   (CSV text)    POST /api/calls/send-now               (same; /trigger-demo kept as alias)
    GET  /api/callbacks                      GET  /api/weather?lat=..&lon=..
    GET  /api/system/checks                  connection checks: backend, database, weather API, Sarvam, phone line
    GET  /api/usage   POST /api/usage        calls, billed minutes and an estimated amount from Sarvam's records; POST sets the
                                             per-minute rate {"sarvam_rate": 3.5} (no balance: Sarvam has no API for it)

Phone numbers are masked in every response and never logged. CORS allows only the origins in GATE0_CORS_ORIGINS
(default: the local dashboard); set it to the hosted dashboard's address in production. There is no login yet.
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .cli import ENV_FILE, load_env_file
from .db import is_postgres
from .service import DashboardService
from .system import SystemChecks

MAX_BODY = 2 * 1024 * 1024
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def make_handler(service: DashboardService, origins: set[str], system: SystemChecks | None = None, token: str = ""):
    """token: when set, every /api call except /api/health must send it as the X-API-Token header."""
    system = system or SystemChecks(service)
    token_bytes = token.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):            # no request logging: URLs and bodies could hold farmer data
            pass

        def _cors(self):
            origin = self.headers.get("Origin", "")
            if "*" in origins or origin in origins:
                self.send_header("Access-Control-Allow-Origin", "*" if "*" in origins else origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept, X-API-Token")

        def _denied(self, path: str) -> bool:
            """True (after answering 401) when a token is required and the request does not carry it."""
            if not token or path == "/api/health":
                return False
            sent = self.headers.get("X-API-Token", "").encode("utf-8")
            if hmac.compare_digest(sent, token_bytes):
                return False
            self._send(401, {"error": "unauthorized"})
            return True

        def _send(self, code: int, body) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> str:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("request body is too large")
            return self.rfile.read(n).decode("utf-8-sig") if n else ""

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            path = u.path.rstrip("/")
            if self._denied(path):
                return
            try:
                if path == "/api/health":
                    return self._send(200, {"status": "ok", "service": "Agrythm Connect API"})
                if path == "/api/calls":
                    calls = service.calls()
                    limit = int(q["limit"][0]) if "limit" in q else None
                    return self._send(200, calls[:limit] if limit else calls)
                if path.startswith("/api/calls/"):
                    call = service.call(urllib.parse.unquote(path[len("/api/calls/"):]))
                    return self._send(200, call) if call else self._send(404, {"error": "Call not found"})
                if path == "/api/farmers":
                    return self._send(200, service.farmers())
                if path == "/api/callbacks":
                    return self._send(200, service.callbacks())
                if path == "/api/alerts":
                    return self._send(200, service.alerts())
                if path == "/api/orchestrator/status":
                    return self._send(200, service.status())
                if path == "/api/system/checks":
                    return self._send(200, system.checks(refresh="refresh" in q))
                if path == "/api/usage":
                    return self._send(200, system.usage(refresh="refresh" in q))
                if path == "/api/weather":
                    w = service.weather_for(float(q["lat"][0]), float(q["lon"][0]))
                    return self._send(200, w) if w else self._send(404, {"error": "No weather for these coordinates"})
            except (KeyError, ValueError):
                return self._send(400, {"error": "bad request"})
            except Exception:
                return self._send(500, {"error": "server error"})
            self._send(404, {"error": "not found"})

        def do_PUT(self):
            path = urllib.parse.urlparse(self.path).path.rstrip("/")
            if self._denied(path):
                return
            try:
                body = self._body()
                if path.startswith("/api/farmers/") and path != "/api/farmers/import":
                    fields = json.loads(body or "{}")
                    if not isinstance(fields, dict):
                        raise ValueError("expected a JSON object")
                    return self._send(200, service.update_farmer(urllib.parse.unquote(path[len("/api/farmers/"):]), fields))
            except KeyError:
                return self._send(404, {"error": "Farmer not found"})
            except json.JSONDecodeError:
                return self._send(400, {"error": "invalid JSON"})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception:
                return self._send(500, {"error": "server error"})
            self._send(404, {"error": "not found"})

        do_PATCH = do_PUT

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path.rstrip("/")
            if self._denied(path):
                return
            try:
                body = self._body()
                if path.startswith("/api/farmers/") and path.endswith("/call"):
                    fid = urllib.parse.unquote(path[len("/api/farmers/"):-len("/call")])
                    fields = json.loads(body or "{}")
                    mode = fields.get("mode", "retry") if isinstance(fields, dict) else "retry"
                    return self._send(202, service.manual_call(fid, mode))
                if path == "/api/farmers":
                    fields = json.loads(body or "{}")
                    if not isinstance(fields, dict):
                        raise ValueError("expected a JSON object")
                    return self._send(201, service.add_farmer(fields))
                if path == "/api/farmers/import":
                    try:
                        return self._send(200, service.import_csv(body))
                    except ValueError as exc:         # messages name rows and IDs, never phone numbers
                        return self._send(400, {"error": str(exc)})
                if path in ("/api/calls/send-now", "/api/calls/trigger-demo", "/api/orchestrator/run-now"):
                    day = service._now().date()
                    if not service.start_fire(day):
                        return self._send(409, {"error": "a send is already in progress"})
                    return self._send(202, {"started": True, "date": day.isoformat(), "callMode": service.dialler.mode})
                if path == "/api/tick":
                    return self._send(202, {"started": service.start_tick(), "at": service._now().isoformat(timespec="seconds")})
                if path == "/api/usage":
                    fields = json.loads(body or "{}")
                    if not isinstance(fields, dict) or "sarvam_rate" not in fields:
                        return self._send(400, {"error": 'Field "sarvam_rate" (rupees a minute) is required'})
                    return self._send(200, system.set_rate(fields["sarvam_rate"]))
                if path == "/api/orchestrator/auto-dispatch":
                    enabled = json.loads(body or "{}").get("enabled")
                    if enabled is None:
                        return self._send(400, {"error": 'Field "enabled" (boolean) is required'})
                    return self._send(200, service.set_auto_dispatch(bool(enabled)))
            except KeyError:
                return self._send(404, {"error": "Farmer not found"})
            except json.JSONDecodeError:
                return self._send(400, {"error": "invalid JSON"})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception:
                return self._send(500, {"error": "server error"})
            self._send(404, {"error": "not found"})

    return Handler


def run(port: int | None = None) -> None:
    load_env_file(ENV_FILE)
    # GATE0_DATABASE_URL (a postgres:// address, Supabase) wins; otherwise the SQLite file in GATE0_DB
    db = (os.environ.get("GATE0_DATABASE_URL") or os.environ.get("GATE0_DB")
          or str(Path(__file__).resolve().parent.parent / "weathercall.db"))
    token = os.environ.get("GATE0_API_TOKEN", "")
    host = os.environ.get("GATE0_API_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise SystemExit("GATE0_API_TOKEN must be set when the API listens on a public address (GATE0_API_HOST).")
    service = DashboardService(db)
    origins = {o.strip() for o in os.environ.get("GATE0_CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()}
    port = port or int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer((host, port), make_handler(service, origins, token=token))
    threading.Thread(target=service.scheduler_loop, daemon=True).start()   # callbacks, and the daily send if switched on
    print(f"Agrythm Connect API on http://{host}:{port}  (database: {'Postgres (Supabase)' if is_postgres(db) else 'SQLite file'}; calls: {service.dialler.mode}; "
          f"weather: {'open-meteo' if service.real_weather else 'mock'}; daily auto-send: "
          f"{'ON' if service.auto_dispatch_enabled() else 'off'})" + (f"\n  note: {service.note}" if service.note else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAPI stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
