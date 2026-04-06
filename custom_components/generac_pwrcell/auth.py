"""Authentication manager for the Generac PWRcell / Neurio cloud API.

The Generac PWRcell mobile app (com.neurio.generachome) uses a custom
session API on top of AWS Cognito — NOT the old Neurio OAuth2 grant flow.

Discovered endpoints (reverse-engineered from app traffic):
  Sign-in:  POST https://generac-api.neur.io/sessions/v1/signin
  Refresh:  POST https://generac-api.neur.io/sessions/v2/refresh/token

Sign-in request:
  Authorization: Basic base64(CLIENT_ID:CLIENT_SECRET)
  Content-Type:  application/json
  User-Agent:    GeneracHome/38904 CFNetwork/3860.400.51 Darwin/25.3.0
  Body:          {"email": "<email>", "password": "<password>"}

Sign-in response:
  {
    "access_token":  "<Cognito JWT>",
    "id_token":      "<Cognito ID JWT>",
    "refresh_token": "<opaque>",
    "token_type":    "Bearer",
    "expires_in":    3600,
    "user_id":       "<UUID>",
    "authChallenge": null,
    "challengeSession": null
  }

Refresh request (no Authorization header):
  Content-Type: application/json
  User-Agent:   GeneracHome/38904 CFNetwork/3860.400.51 Darwin/25.3.0
  Body:         {"userId": "<UUID>", "refreshToken": "<token>"}
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

import aiohttp

from .const import (
    APP_BUILD,
    APP_CLIENT_ID,
    APP_CLIENT_SECRET,
    APP_USER_AGENT,
    APP_VERSION,
    DEFAULT_API_BASE,
)

_LOGGER = logging.getLogger(__name__)

# Refresh this many seconds before the token actually expires
_REFRESH_BUFFER_SECONDS = 300

# Basic auth header value — pre-computed from the known app credentials
_BASIC_AUTH = "Basic " + base64.b64encode(
    f"{APP_CLIENT_ID}:{APP_CLIENT_SECRET}".encode()
).decode()

# Headers that mimic the mobile app — required; the API rejects unknown clients
_APP_HEADERS = {
    "user-agent": APP_USER_AGENT,
    "mobileappversion": APP_VERSION,
    "mobileappbuildnumber": APP_BUILD,
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
}


class AuthError(Exception):
    """Raised on any authentication failure."""


class GeneracAuth:
    """Manages Generac session tokens for the cloud API.

    Usage:
        auth = GeneracAuth(session, email, password)
        token = await auth.async_get_access_token()   # auto-refreshes
        data  = await auth.async_get(url)
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        api_base: str = DEFAULT_API_BASE,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password

        # Derive auth URLs from api_base so a local mock server can be used.
        self._signin_url = f"{api_base}/sessions/v1/signin"
        self._refresh_url = f"{api_base}/sessions/v2/refresh/token"

        self._access_token: str | None = None
        self._id_token: str | None = None        # used by data API endpoints
        self._refresh_token: str | None = None
        self._user_id: str | None = None
        self._expires_at: float = 0.0

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def user_id(self) -> str | None:
        return self._user_id

    @property
    def id_token(self) -> str | None:
        """The Cognito ID token — required as Bearer for data API endpoints."""
        return self._id_token

    def is_token_valid(self) -> bool:
        return (
            self._access_token is not None
            and time.monotonic() < self._expires_at - _REFRESH_BUFFER_SECONDS
        )

    async def async_get_access_token(self) -> str:
        """Return a valid access_token, signing in or refreshing as needed."""
        if self.is_token_valid():
            return self._access_token  # type: ignore[return-value]

        if self._refresh_token and self._user_id:
            try:
                await self._async_refresh()
                return self._access_token  # type: ignore[return-value]
            except AuthError as exc:
                _LOGGER.warning("Token refresh failed (%s), re-signing in", exc)

        await self._async_signin()
        return self._access_token  # type: ignore[return-value]

    async def async_get_id_token(self) -> str:
        """Return a valid id_token (used as Bearer by data API endpoints).

        The id_token is issued alongside the access_token and shares its
        expiry, so ensuring a valid access_token also ensures a valid id_token.
        """
        await self.async_get_access_token()
        if not self._id_token:
            raise AuthError("No id_token available after authentication.")
        return self._id_token

    async def async_get(self, url: str, params: dict | None = None, use_id_token: bool = False) -> Any:
        """Authenticated GET. Set use_id_token=True for data API endpoints."""
        return await self._async_request("GET", url, params=params, use_id_token=use_id_token)

    async def async_post(self, url: str, json: dict | None = None) -> Any:
        """Authenticated POST request (uses access_token)."""
        return await self._async_request("POST", url, json=json)

    # ── Sign-in ───────────────────────────────────────────────────────────────

    async def _async_signin(self) -> None:
        """Full sign-in with email + password."""
        _LOGGER.debug("Signing in to Generac API as %s", self._email)
        headers = {
            **_APP_HEADERS,
            "Authorization": _BASIC_AUTH,
            "content-type": "application/json",
        }
        payload = {"email": self._email, "password": self._password}

        try:
            async with self._session.post(
                self._signin_url, headers=headers, json=payload
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status != 200:
                    raise AuthError(
                        f"Sign-in failed ({resp.status}): "
                        f"{body.get('message', body.get('error', 'unknown'))}"
                    )
        except aiohttp.ClientError as exc:
            raise AuthError(f"Network error during sign-in: {exc}") from exc

        self._store_tokens(body)
        _LOGGER.debug("Sign-in successful, user_id=%s", self._user_id)

    # ── Refresh ───────────────────────────────────────────────────────────────

    async def _async_refresh(self) -> None:
        """Refresh the access token using the stored refresh token."""
        _LOGGER.debug("Refreshing Generac access token")
        headers = {
            **_APP_HEADERS,
            "content-type": "application/json",
        }
        payload = {
            "userId": self._user_id,
            "refreshToken": self._refresh_token,
        }

        try:
            async with self._session.post(
                self._refresh_url, headers=headers, json=payload
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status != 200:
                    raise AuthError(
                        f"Token refresh failed ({resp.status}): "
                        f"{body.get('message', body.get('error', 'unknown'))}"
                    )
        except aiohttp.ClientError as exc:
            raise AuthError(f"Network error during token refresh: {exc}") from exc

        self._store_tokens(body)
        _LOGGER.debug("Token refreshed successfully")

    # ── Generic request ───────────────────────────────────────────────────────

    async def _async_request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        json: dict | None = None,
        use_id_token: bool = False,
    ) -> Any:
        token = await self.async_get_id_token() if use_id_token else await self.async_get_access_token()
        headers = {
            **_APP_HEADERS,
            "Authorization": f"Bearer {token}",
            "content-type": "application/json",
        }

        try:
            async with self._session.request(
                method, url, headers=headers, params=params, json=json
            ) as resp:
                if resp.status == 401:
                    # Force a fresh sign-in and retry once
                    _LOGGER.debug("Got 401, forcing re-authentication")
                    self._access_token = None
                    self._refresh_token = None
                    await self._async_signin()
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    async with self._session.request(
                        method, url, headers=headers, params=params, json=json
                    ) as resp2:
                        resp2.raise_for_status()
                        return await resp2.json(content_type=None)

                resp.raise_for_status()
                return await resp.json(content_type=None)

        except aiohttp.ClientResponseError as exc:
            raise AuthError(f"API request to {url} returned {exc.status}") from exc
        except aiohttp.ClientError as exc:
            raise AuthError(f"Network error calling {url}: {exc}") from exc

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _store_tokens(self, body: dict) -> None:
        self._access_token = body["access_token"]
        # id_token is used as Bearer for data API endpoints (telemetry, homes, etc.)
        if "id_token" in body:
            self._id_token = body["id_token"]
        # refresh_token only present on full sign-in; preserve existing on refresh
        if "refresh_token" in body:
            self._refresh_token = body["refresh_token"]
        if "user_id" in body:
            self._user_id = body["user_id"]
        expires_in = int(body.get("expires_in", 3600))
        self._expires_at = time.monotonic() + expires_in

    # ── Validation (config flow) ───────────────────────────────────────────────

    @classmethod
    async def async_validate(
        cls,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        api_base: str = DEFAULT_API_BASE,
    ) -> str:
        """Sign in and return user_id. Raises AuthError on failure."""
        auth = cls(session, email, password, api_base=api_base)
        await auth._async_signin()
        if not auth.user_id:
            raise AuthError("Sign-in succeeded but no user_id returned.")
        return auth.user_id
