#!/usr/bin/env python3
"""Local mock server for Generac PWRcell API development & testing.

Simulates the generac-api.neur.io endpoints so the integration can be
tested against your local Home Assistant instance without hitting the
real cloud API.

Usage:
    python mock_server/server.py [--port 8080] [--host 0.0.0.0]

Then in the Home Assistant config flow set the API base URL to:
    http://<your-machine-ip>:8080

Credentials: any non-empty email/password are accepted.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("mock_server")

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

# ── Fake token store ───────────────────────────────────────────────────────────
_USER_ID = "mock-user-uuid-0001"
_ACCESS_TOKEN = "mock-access-token"
_ID_TOKEN = "mock-id-token"
_REFRESH_TOKEN = "mock-refresh-token"

_SIGNIN_RESPONSE = {
    "access_token": _ACCESS_TOKEN,
    "id_token": _ID_TOKEN,
    "refresh_token": _REFRESH_TOKEN,
    "token_type": "Bearer",
    "expires_in": 3600,
    "user_id": _USER_ID,
    "authChallenge": None,
    "challengeSession": None,
}

_REFRESH_RESPONSE = {
    "access_token": _ACCESS_TOKEN + "-refreshed",
    "id_token": _ID_TOKEN + "-refreshed",
    "expires_in": 3600,
}


def _load_fixture(name: str):
    path = FIXTURES / name
    if path.exists():
        return json.loads(path.read_text())
    return None


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default access log
        pass

    # ── Routing ────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/sessions/v1/signin":
            self._handle_signin(body)
        elif path == "/sessions/v2/refresh/token":
            self._handle_refresh(body)
        else:
            self._send(404, {"error": f"Unknown POST path: {path}"})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if not self._check_bearer():
            return

        if path == "/live/v1/homes":
            self._handle_homes()
        elif path.startswith("/live/v2/homes/") and path.endswith("/telemetry"):
            self._handle_telemetry(path, query)
        else:
            self._send(404, {"error": f"Unknown GET path: {path}"})

    # ── Handlers ───────────────────────────────────────────────────────────────

    def _handle_signin(self, body: dict):
        email = body.get("email", "")
        password = body.get("password", "")
        if not email or not password:
            log.warning("Sign-in rejected: missing email or password")
            self._send(401, {"message": "Missing credentials"})
            return

        log.info("Sign-in  email=%s", email)
        self._send(200, _SIGNIN_RESPONSE)

    def _handle_refresh(self, body: dict):
        user_id = body.get("userId", "")
        refresh_token = body.get("refreshToken", "")
        if not user_id or not refresh_token:
            self._send(400, {"message": "Missing userId or refreshToken"})
            return

        log.info("Token refresh  userId=%s", user_id)
        self._send(200, _REFRESH_RESPONSE)

    def _handle_homes(self):
        data = _load_fixture("homes_response.json")
        if data is None:
            self._send(500, {"error": "homes_response.json fixture not found"})
            return
        log.info("GET /live/v1/homes → %d home(s)", len(data))
        self._send(200, data)

    def _handle_telemetry(self, path: str, query: dict):
        # Extract homeId from path: /live/v2/homes/{homeId}/telemetry
        parts = path.strip("/").split("/")
        home_id = parts[3] if len(parts) > 3 else "unknown"
        from_iso = query.get("fromIso", [None])[0]

        data = _load_fixture("telemetry_response.json")
        if data is None:
            self._send(500, {"error": "telemetry_response.json fixture not found"})
            return

        log.info("GET telemetry  homeId=%s  fromIso=%s → %d entry(s)", home_id, from_iso, len(data))
        self._send(200, data)

    # ── Auth check ─────────────────────────────────────────────────────────────

    def _check_bearer(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            log.warning("Missing or malformed Authorization header on %s", self.path)
            self._send(401, {"message": "Unauthorized"})
            return False
        return True

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _send(self, status: int, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Entry point ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Generac PWRcell mock API server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), MockHandler)
    log.info("Mock server listening on http://%s:%d", args.host, args.port)
    log.info("Set API base URL to: http://<your-machine-ip>:%d", args.port)
    log.info("Fixtures directory: %s", FIXTURES)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")


if __name__ == "__main__":
    main()
