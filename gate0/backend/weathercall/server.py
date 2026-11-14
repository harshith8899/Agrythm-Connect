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

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .cli import ENV_FILE, load_env_file
from .db import is_postgres
from .service import DashboardService
from .system import SystemChecks

MAX_BODY = 2 * 1024 * 1024
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

_SIGNING_SECRET = secrets.token_bytes(32)


def _get_signing_secret() -> bytes:
    secret = os.environ.get("GATE0_AUTH_SECRET") or os.environ.get("GATE0_API_TOKEN")
    if secret:
        return hashlib.sha256(secret.encode("utf-8")).digest()
    return _SIGNING_SECRET


def create_session_token(username: str, ttl_seconds: int = 86400 * 7) -> str:
    """Creates an HMAC-signed session token containing the username and expiration timestamp."""
    exp = int(time.time()) + ttl_seconds
    payload = json.dumps({"u": username, "exp": exp}, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_get_signing_secret(), payload, hashlib.sha256).digest()
    p_b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    s_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return f"{p_b64}.{s_b64}"


def verify_session_token(token_str: str) -> bool:
    """Verifies that the session token is signed with the server secret and has not expired."""
    try:
        parts = token_str.strip().split(".")
        if len(parts) != 2:
            return False
        p_b64 = parts[0] + "=" * (-len(parts[0]) % 4)
        s_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(p_b64.encode("ascii"))
        sig = base64.urlsafe_b64decode(s_b64.encode("ascii"))
        expected_sig = hmac.new(_get_signing_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            return False
        data = json.loads(payload.decode("utf-8"))
        return float(data.get("exp", 0)) > time.time()
    except Exception:
        return False


def make_handler(
    service: DashboardService,
    origins: set[str],
    system: SystemChecks | None = None,
    token: str = "",
    admin_user: str | None = None,
    admin_password: str | None = None,
    require_auth: bool | None = None,
):
    """token: when set, every /api call except /api/health must send it as the X-API-Token header or Bearer token."""
    system = system or SystemChecks(service)
    effective_admin_user = admin_user if admin_user is not None else os.environ.get("GATE0_ADMIN_USER", "")
    effective_admin_pass = admin_password if admin_password is not None else os.environ.get("GATE0_ADMIN_PASSWORD", "")
    effective_token = token or os.environ.get("GATE0_API_TOKEN", "")
    if require_auth is None:
        require_auth = bool(effective_token or effective_admin_user or effective_admin_pass)

    def is_valid_token(cand: str) -> bool:
        if not cand:
            return False
        cand_bytes = cand.strip().encode("utf-8")
        if effective_token and hmac.compare_digest(cand_bytes, effective_token.encode("utf-8")):
            return True
        return verify_session_token(cand)

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

        def _extract_token(self) -> str:
            auth = self.headers.get("Authorization", "").strip()
            if auth.lower().startswith("bearer "):
                return auth[7:].strip()
            return self.headers.get("X-API-Token", "").strip()

        def _denied(self, path: str) -> bool:
            """True (after answering 401) when a token is required and the request does not carry it."""
            if path in ("/api/health", "/api/auth/login"):
                return False
            if not require_auth:
                return False
            sent = self._extract_token()
            if sent and is_valid_token(sent):
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
                if path == "/api/auth/login":
                    fields = json.loads(body or "{}")
                    if not isinstance(fields, dict):
                        return self._send(400, {"error": "expected a JSON object"})
                    u = str(fields.get("username", "")).strip()
                    p = str(fields.get("password", "")).strip()
                    admin_u = effective_admin_user.strip()
                    admin_p = effective_admin_pass.strip()
                    if (admin_u and admin_p and
                            hmac.compare_digest(u.encode("utf-8"), admin_u.encode("utf-8")) and
                            hmac.compare_digest(p.encode("utf-8"), admin_p.encode("utf-8"))):
                        session_token = create_session_token(admin_u)
                        return self._send(200, {"token": session_token, "username": admin_u})
                    return self._send(401, {"error": "Invalid username or password"})
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
    admin_user = os.environ.get("GATE0_ADMIN_USER", "")
    admin_password = os.environ.get("GATE0_ADMIN_PASSWORD", "")
    host = os.environ.get("GATE0_API_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1") and not token and not (admin_user and admin_password):
        raise SystemExit("GATE0_API_TOKEN or admin credentials (GATE0_ADMIN_USER/GATE0_ADMIN_PASSWORD) must be set when the API listens on a public address (GATE0_API_HOST).")
    service = DashboardService(db)
    origins = {o.strip() for o in os.environ.get("GATE0_CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()}
    port = port or int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer((host, port), make_handler(service, origins, token=token, admin_user=admin_user, admin_password=admin_password, require_auth=True))
    threading.Thread(target=service.scheduler_loop, daemon=True).start()   # callbacks, and the daily send if switched on
    print(f"Agrythm Connect API on http://{host}:{port}  (database: {'Postgres (Supabase)' if is_postgres(db) else 'SQLite file'}; calls: {service.dialler.mode}; "
          f"weather: {getattr(service._weather, 'label', 'Open-Meteo') if service.real_weather else 'mock'}; daily auto-send: "
          f"{'ON' if service.auto_dispatch_enabled() else 'off'})" + (f"\n  note: {service.note}" if service.note else ""))
    # The host (Render) stops the process on every deploy: stop taking new calls, let the ones on the phone finish (their
    # results are then saved as usual), and only then exit. render.yaml gives the host time to wait (maxShutdownDelaySeconds).
    import signal

    def _stop(signum, frame):
        service.draining = True

        def finish():
            service.wait_idle(float(os.environ.get("GATE0_DRAIN_SECONDS", 240)))
            server.shutdown()
        threading.Thread(target=finish, daemon=True).start()
    try:
        signal.signal(signal.SIGTERM, _stop)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAPI stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
