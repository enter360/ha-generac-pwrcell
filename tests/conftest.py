"""Shared test fixtures and Home Assistant module stubs.

Because this is a standalone custom component (not installed inside a running
Home Assistant instance), we stub out the homeassistant package so the
component modules can be imported during tests without HA installed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── sys.path ──────────────────────────────────────────────────────────────────
# Ensure the repo root is on the path so `custom_components` is importable.
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ── Home Assistant stubs ──────────────────────────────────────────────────────
# These must be registered before any custom_components.* import happens.


class _DataUpdateCoordinator:
    """Minimal stub that satisfies PWRcellCoordinator's super().__init__ call."""

    def __init__(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None


class _UpdateFailed(Exception):
    """Stub for homeassistant.helpers.update_coordinator.UpdateFailed."""


_update_coordinator_mod = MagicMock()
_update_coordinator_mod.DataUpdateCoordinator = _DataUpdateCoordinator
_update_coordinator_mod.UpdateFailed = _UpdateFailed

_ha_const_mod = MagicMock()
_ha_const_mod.CONF_EMAIL = "email"
_ha_const_mod.CONF_PASSWORD = "password"
_ha_const_mod.Platform = MagicMock()
_ha_const_mod.Platform.SENSOR = "sensor"

_stubs: dict = {
    "homeassistant": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.update_coordinator": _update_coordinator_mod,
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.selector": MagicMock(),
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.const": _ha_const_mod,
    "voluptuous": MagicMock(),
}
for _name, _stub in _stubs.items():
    sys.modules.setdefault(_name, _stub)


# ── Fixture helpers ───────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with open(FIXTURES_DIR / name) as fh:
        return json.load(fh)


@pytest.fixture
def homes_response():
    return load_fixture("homes_response.json")


@pytest.fixture
def telemetry_response():
    return load_fixture("telemetry_response.json")
