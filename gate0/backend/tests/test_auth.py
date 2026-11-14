import json
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from weathercall.adapters.dialers import MockDialler
from weathercall.server import create_session_token, make_handler, verify_session_token
from weathercall.service import DashboardService


@pytest.fixture
def auth_api(tmp_path, monkeypatch):
    monkeypatch.setenv("GATE0_ADMIN_USER", "testadmin")
    monkeypatch.setenv("GATE0_ADMIN_PASSWORD", "testpass123")
    monkeypatch.setenv("GATE0_API_TOKEN", "apikey-secret")

    s = DashboardService(str(tmp_path / "test.db"), dialler=MockDialler())
    srv = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(
            s,
            {"*"},
            token="apikey-secret",
            admin_user="testadmin",
            admin_password="testpass123",
            require_auth=True,
        ),
    )
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, data=None, token=None, auth_bearer=None, method=None):
        req = urllib.request.Request(
            base + path,
            data=data,
            method=method or ("POST" if data is not None else "GET"),
        )
        if token:
            req.add_header("X-API-Token", token)
        if auth_bearer:
            req.add_header("Authorization", f"Bearer {auth_bearer}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            try:
                body = json.load(e)
            except Exception:
                body = None
            return e.code, body

    yield call
    srv.shutdown()
    srv.server_close()


def test_session_token_generation_and_verification():
    tok = create_session_token("testadmin", ttl_seconds=3600)
    assert verify_session_token(tok) is True
    # Tampered token fails
    parts = tok.split(".")
    tampered = parts[0] + ".invalidsig"
    assert verify_session_token(tampered) is False
    # Expired token fails
    expired_tok = create_session_token("testadmin", ttl_seconds=-10)
    assert verify_session_token(expired_tok) is False


def test_auth_login_success(auth_api):
    payload = json.dumps({"username": "testadmin", "password": "testpass123"}).encode()
    status, body = auth_api("/api/auth/login", data=payload)
    assert status == 200
    assert "token" in body
    assert body["username"] == "testadmin"
    assert verify_session_token(body["token"]) is True


def test_auth_login_invalid_credentials(auth_api):
    # Bad password
    payload = json.dumps({"username": "testadmin", "password": "wrongpassword"}).encode()
    status, body = auth_api("/api/auth/login", data=payload)
    assert status == 401

    # Bad user
    payload = json.dumps({"username": "intruder", "password": "testpass123"}).encode()
    status, body = auth_api("/api/auth/login", data=payload)
    assert status == 401


def test_health_endpoint_is_unauthenticated(auth_api):
    status, body = auth_api("/api/health")
    assert status == 200
    assert body["status"] == "ok"


def test_protected_endpoints_reject_unauthenticated(auth_api):
    status, body = auth_api("/api/farmers")
    assert status == 401

    status, body = auth_api("/api/calls")
    assert status == 401


def test_protected_endpoints_accept_valid_bearer_session_token(auth_api):
    login_payload = json.dumps({"username": "testadmin", "password": "testpass123"}).encode()
    _, login_body = auth_api("/api/auth/login", data=login_payload)
    session_token = login_body["token"]

    status, body = auth_api("/api/farmers", auth_bearer=session_token)
    assert status == 200
    assert isinstance(body, list)


def test_protected_endpoints_accept_valid_api_token(auth_api):
    status, body = auth_api("/api/farmers", token="apikey-secret")
    assert status == 200
    assert isinstance(body, list)


def test_protected_endpoints_reject_invalid_bearer_token(auth_api):
    status, body = auth_api("/api/farmers", auth_bearer="fake.invalid.token")
    assert status == 401
