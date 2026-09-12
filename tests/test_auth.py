"""Unit tests for GeneracAuth."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.generac_pwrcell.auth import AuthError, GeneracAuth
from custom_components.generac_pwrcell.const import DEFAULT_API_BASE

MOCK_BASE = "http://localhost:8080"

# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_SIGNIN_RESPONSE = {
    "access_token": "access-tok-123",
    "id_token": "id-tok-abc",
    "refresh_token": "refresh-tok-xyz",
    "token_type": "Bearer",
    "expires_in": 3600,
    "user_id": "user-uuid-001",
}

VALID_REFRESH_RESPONSE = {
    "access_token": "access-tok-refreshed",
    "id_token": "id-tok-refreshed",
    "expires_in": 3600,
}


def _mock_session(post_status: int = 200, post_json=None, request_status: int = 200, request_json=None):
    """Build an aiohttp.ClientSession mock with configurable POST and request responses."""
    session = MagicMock()

    def _make_ctx(status, data):
        resp = AsyncMock()
        resp.status = status
        resp.json = AsyncMock(return_value=data if data is not None else {})
        resp.raise_for_status = MagicMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx, resp

    post_ctx, post_resp = _make_ctx(post_status, post_json if post_json is not None else VALID_SIGNIN_RESPONSE)
    session.post = MagicMock(return_value=post_ctx)

    req_ctx, req_resp = _make_ctx(request_status, request_json if request_json is not None else {"data": "ok"})
    session.request = MagicMock(return_value=req_ctx)

    return session, post_resp, req_resp


# ── is_token_valid ────────────────────────────────────────────────────────────


def test_is_token_valid_no_token():
    auth = GeneracAuth(MagicMock(), "a@b.com", "pw", api_base=MOCK_BASE)
    assert auth.is_token_valid() is False


def test_is_token_valid_expired():
    auth = GeneracAuth(MagicMock(), "a@b.com", "pw", api_base=MOCK_BASE)
    auth._access_token = "tok"
    auth._expires_at = time.monotonic() - 10  # already expired
    assert auth.is_token_valid() is False


def test_is_token_valid_within_buffer():
    auth = GeneracAuth(MagicMock(), "a@b.com", "pw", api_base=MOCK_BASE)
    auth._access_token = "tok"
    # expires_at is 200 s from now — less than the 300 s buffer
    auth._expires_at = time.monotonic() + 200
    assert auth.is_token_valid() is False


def test_is_token_valid_ok():
    auth = GeneracAuth(MagicMock(), "a@b.com", "pw", api_base=MOCK_BASE)
    auth._access_token = "tok"
    auth._expires_at = time.monotonic() + 400  # comfortably ahead of buffer
    assert auth.is_token_valid() is True


# ── URL derivation ────────────────────────────────────────────────────────────


def test_urls_use_custom_base():
    auth = GeneracAuth(MagicMock(), "a@b.com", "pw", api_base=MOCK_BASE)
    assert auth._signin_url == f"{MOCK_BASE}/sessions/v1/signin"
    assert auth._refresh_url == f"{MOCK_BASE}/sessions/v2/refresh/token"


def test_urls_default_to_production():
    auth = GeneracAuth(MagicMock(), "a@b.com", "pw")
    assert auth._signin_url.startswith(DEFAULT_API_BASE)
    assert auth._refresh_url.startswith(DEFAULT_API_BASE)


# ── Sign-in ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signin_success():
    session, _, _ = _mock_session(post_json=VALID_SIGNIN_RESPONSE)
    auth = GeneracAuth(session, "user@example.com", "secret", api_base=MOCK_BASE)

    token = await auth.async_get_access_token()

    assert token == "access-tok-123"
    assert auth.user_id == "user-uuid-001"
    assert auth.id_token == "id-tok-abc"
    assert auth._refresh_token == "refresh-tok-xyz"
    assert auth.is_token_valid()


@pytest.mark.asyncio
async def test_signin_401_raises_auth_error():
    session, _, _ = _mock_session(post_status=401, post_json={"message": "Unauthorized"})
    auth = GeneracAuth(session, "bad@user.com", "wrong", api_base=MOCK_BASE)

    with pytest.raises(AuthError, match="401"):
        await auth.async_get_access_token()


@pytest.mark.asyncio
async def test_signin_network_error_raises_auth_error():
    import aiohttp

    session = MagicMock()
    session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("refused"))

    auth = GeneracAuth(session, "user@example.com", "pw", api_base=MOCK_BASE)

    with pytest.raises(AuthError, match="Network error"):
        await auth.async_get_access_token()


# ── Token refresh ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_uses_stored_refresh_token():
    session, _, _ = _mock_session(post_json=VALID_SIGNIN_RESPONSE)
    auth = GeneracAuth(session, "u@e.com", "pw", api_base=MOCK_BASE)

    # Simulate a previous sign-in that stored tokens but is about to expire
    auth._access_token = "old-tok"
    auth._refresh_token = "stored-refresh-tok"
    auth._user_id = "user-uuid-001"
    auth._expires_at = time.monotonic() - 1  # expired

    # Make refresh return a new token
    session.post = MagicMock(
        return_value=_make_post_ctx(200, VALID_REFRESH_RESPONSE)
    )

    token = await auth.async_get_access_token()
    assert token == "access-tok-refreshed"


@pytest.mark.asyncio
async def test_refresh_failure_falls_back_to_signin():
    """When refresh returns non-200, auth should fall back to full sign-in."""
    session = MagicMock()

    call_count = {"n": 0}

    def _post_side_effect(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call = refresh → fail
            return _make_post_ctx(400, {"message": "Bad refresh"})
        # Second call = full sign-in → succeed
        return _make_post_ctx(200, VALID_SIGNIN_RESPONSE)

    session.post = MagicMock(side_effect=_post_side_effect)

    auth = GeneracAuth(session, "u@e.com", "pw", api_base=MOCK_BASE)
    auth._access_token = "old"
    auth._refresh_token = "old-refresh"
    auth._user_id = "user-uuid-001"
    auth._expires_at = time.monotonic() - 1

    token = await auth.async_get_access_token()
    assert token == "access-tok-123"
    assert call_count["n"] == 2  # refresh attempt + signin


# ── async_validate ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_validate_success():
    session, _, _ = _mock_session(post_json=VALID_SIGNIN_RESPONSE)
    user_id = await GeneracAuth.async_validate(session, "u@e.com", "pw", api_base=MOCK_BASE)
    assert user_id == "user-uuid-001"


@pytest.mark.asyncio
async def test_async_validate_bad_credentials():
    session, _, _ = _mock_session(post_status=401, post_json={"message": "Unauthorized"})
    with pytest.raises(AuthError):
        await GeneracAuth.async_validate(session, "u@e.com", "bad", api_base=MOCK_BASE)


# ── _store_tokens edge cases ──────────────────────────────────────────────────


def test_store_tokens_preserves_refresh_token_on_refresh():
    """Refresh response has no refresh_token — existing one must be preserved."""
    auth = GeneracAuth(MagicMock(), "u@e.com", "pw", api_base=MOCK_BASE)
    auth._refresh_token = "original-refresh"

    auth._store_tokens(VALID_REFRESH_RESPONSE)  # no refresh_token key

    assert auth._refresh_token == "original-refresh"
    assert auth._access_token == "access-tok-refreshed"


def test_store_tokens_replaces_refresh_token_on_signin():
    auth = GeneracAuth(MagicMock(), "u@e.com", "pw", api_base=MOCK_BASE)
    auth._refresh_token = "old-refresh"

    auth._store_tokens(VALID_SIGNIN_RESPONSE)

    assert auth._refresh_token == "refresh-tok-xyz"


# ── Helper ────────────────────────────────────────────────────────────────────


def _make_post_ctx(status: int, data: dict):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    resp.raise_for_status = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx
