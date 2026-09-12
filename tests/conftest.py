"""Shared test fixtures and Home Assistant module stubs.

Because this is a standalone custom component (not installed inside a running
Home Assistant instance), we stub out the homeassistant package so the
component modules can be imported during tests without HA installed.
"""
from __future__ import annotations

import enum as _enum
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import dataclasses

import pytest

# ── Python 3.9 compat ─────────────────────────────────────────────────────────
# @dataclass(kw_only=True) was added in 3.10.  On 3.9 we strip the argument
# AND inject None defaults for any unannotated fields, which prevents the
# "non-default argument follows default argument" error that kw_only normally
# sidesteps.
if sys.version_info < (3, 10):
    _orig_dataclass = dataclasses.dataclass

    def _compat_dataclass(*args, **kwargs):
        kw_only_stripped = "kw_only" in kwargs
        kwargs.pop("kw_only", None)

        def _inject_defaults(cls):
            if kw_only_stripped:
                for name in list(cls.__annotations__):
                    if name not in cls.__dict__:
                        setattr(cls, name, None)

        if args and isinstance(args[0], type):
            _inject_defaults(args[0])
            return _orig_dataclass(*args, **kwargs)

        orig_decorator = _orig_dataclass(*args, **kwargs)

        def decorator(cls):
            _inject_defaults(cls)
            return orig_decorator(cls)

        return decorator

    dataclasses.dataclass = _compat_dataclass  # type: ignore[assignment]

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
_ha_const_mod.PERCENTAGE = "%"
_ha_const_mod.UnitOfElectricPotential = MagicMock()
_ha_const_mod.UnitOfElectricPotential.VOLT = "V"
_ha_const_mod.UnitOfEnergy = MagicMock()
_ha_const_mod.UnitOfEnergy.WATT_HOUR = "Wh"
_ha_const_mod.UnitOfPower = MagicMock()
_ha_const_mod.UnitOfPower.WATT = "W"
_ha_const_mod.UnitOfTemperature = MagicMock()
_ha_const_mod.UnitOfTemperature.CELSIUS = "°C"
_ha_const_mod.UnitOfTime = MagicMock()
_ha_const_mod.UnitOfTime.SECONDS = "s"


def _callback_passthrough(fn):
    """Stub for homeassistant.core.callback — just returns the function unchanged."""
    return fn


_ha_core_mod = MagicMock()
_ha_core_mod.callback = _callback_passthrough
_ha_core_mod.HomeAssistant = MagicMock


class _RestoreSensor:
    """Minimal RestoreSensor stub."""

    async def async_added_to_hass(self):
        pass

    async def async_get_last_sensor_data(self):
        return None


class _CoordinatorEntity:
    """Minimal CoordinatorEntity stub."""

    # Allow CoordinatorEntity[SomeType] generic syntax used in sensor.py
    def __class_getitem__(cls, _item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def async_added_to_hass(self):
        pass

    @property
    def available(self):
        return True

    def async_write_ha_state(self):
        pass


class _EntityCategory(_enum.Enum):
    DIAGNOSTIC = "diagnostic"
    CONFIG = "config"

_ha_entity_mod = MagicMock()
_ha_entity_mod.EntityCategory = _EntityCategory


@dataclasses.dataclass(frozen=True)
class _SensorEntityDescription:
    """Frozen dataclass base matching the HA SensorEntityDescription fields used here."""
    key: str = ""
    name: str | None = None
    native_unit_of_measurement: str | None = None
    device_class: object = None
    state_class: object = None
    icon: str | None = None
    suggested_display_precision: int | None = None
    entity_registry_enabled_default: bool = True
    # data_key with a default so Python 3.9 ordering rules are satisfied;
    # the compat shim also injects None on the child class for the same reason.
    data_key: str = ""
    suggested_unit_of_measurement: str | None = None
    entity_category: object = None


_sensor_mod = MagicMock()
_sensor_mod.RestoreSensor = _RestoreSensor
_sensor_mod.SensorDeviceClass = MagicMock()
_sensor_mod.SensorEntity = MagicMock
_sensor_mod.SensorEntityDescription = _SensorEntityDescription
_sensor_mod.SensorStateClass = MagicMock()

_coordinator_mod_full = MagicMock()
_coordinator_mod_full.DataUpdateCoordinator = _DataUpdateCoordinator
_coordinator_mod_full.UpdateFailed = _UpdateFailed
_coordinator_mod_full.CoordinatorEntity = _CoordinatorEntity

_stubs: dict = {
    "homeassistant": MagicMock(),
    "homeassistant.core": _ha_core_mod,
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.update_coordinator": _coordinator_mod_full,
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.selector": MagicMock(),
    "homeassistant.helpers.device_registry": MagicMock(),
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity_mod,
    "homeassistant.components": MagicMock(),
    "homeassistant.components.sensor": _sensor_mod,
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.const": _ha_const_mod,
    "voluptuous": MagicMock(),
}
for _name, _stub in _stubs.items():
    sys.modules[_name] = _stub


# ── Fixture helpers ───────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    with open(FIXTURES_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def homes_response():
    return load_fixture("homes_response.json")


@pytest.fixture
def telemetry_response():
    return load_fixture("telemetry_response.json")
