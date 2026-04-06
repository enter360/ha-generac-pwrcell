"""Unit tests for PWRcellIntegratedEnergySensor."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.generac_pwrcell.const import (
    SENSOR_BATTERY_CHARGE_ENERGY,
    SENSOR_BATTERY_DISCHARGE_ENERGY,
    SENSOR_BATTERY_POWER,
    SENSOR_GRID_EXPORT_ENERGY,
    SENSOR_GRID_EXPORT_POWER,
    SENSOR_GRID_IMPORT_ENERGY,
    SENSOR_GRID_IMPORT_POWER,
    SENSOR_HOME_ENERGY,
    SENSOR_HOME_POWER,
)
from custom_components.generac_pwrcell.sensor import PWRcellIntegratedEnergySensor

HOME_ID = "home-test-001"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_coord(power_w: float | None = None, power_key: str = SENSOR_BATTERY_POWER):
    coord = MagicMock()
    coord.data = {power_key: power_w}
    coord.system_serial = "S001"
    return coord


def _make_sensor(
    source_key: str,
    unique_id_suffix: str,
    sign: str,
    power_w: float | None = None,
    coordinator=None,
) -> PWRcellIntegratedEnergySensor:
    """Instantiate a sensor with HA super().__init__ bypassed."""
    coord = coordinator or _make_coord(power_w, source_key)
    sensor = PWRcellIntegratedEnergySensor.__new__(PWRcellIntegratedEnergySensor)
    sensor.coordinator = coord
    sensor._source_key = source_key
    sensor._sign = sign
    sensor._energy_wh = 0.0
    sensor._last_update_time = None
    sensor._attr_unique_id = f"{HOME_ID}_{unique_id_suffix}"
    sensor._attr_name = unique_id_suffix.replace("_", " ").title()
    sensor.async_write_ha_state = MagicMock()
    return sensor


def _discharge(power_w=None, **kw):
    return _make_sensor(SENSOR_BATTERY_POWER, SENSOR_BATTERY_DISCHARGE_ENERGY, "positive", power_w, **kw)


def _charge(power_w=None, **kw):
    return _make_sensor(SENSOR_BATTERY_POWER, SENSOR_BATTERY_CHARGE_ENERGY, "negative", power_w, **kw)


def _grid_import(power_w=None):
    return _make_sensor(SENSOR_GRID_IMPORT_POWER, SENSOR_GRID_IMPORT_ENERGY, "positive",
                        coordinator=_make_coord(power_w, SENSOR_GRID_IMPORT_POWER))


def _grid_export(power_w=None):
    return _make_sensor(SENSOR_GRID_EXPORT_POWER, SENSOR_GRID_EXPORT_ENERGY, "positive",
                        coordinator=_make_coord(power_w, SENSOR_GRID_EXPORT_POWER))


def _home(power_w=None):
    return _make_sensor(SENSOR_HOME_POWER, SENSOR_HOME_ENERGY, "positive",
                        coordinator=_make_coord(power_w, SENSOR_HOME_POWER))


# ── unique_id ─────────────────────────────────────────────────────────────────


def test_discharge_unique_id():
    assert SENSOR_BATTERY_DISCHARGE_ENERGY in _discharge()._attr_unique_id


def test_charge_unique_id():
    assert SENSOR_BATTERY_CHARGE_ENERGY in _charge()._attr_unique_id


def test_grid_import_unique_id():
    assert SENSOR_GRID_IMPORT_ENERGY in _grid_import()._attr_unique_id


def test_grid_export_unique_id():
    assert SENSOR_GRID_EXPORT_ENERGY in _grid_export()._attr_unique_id


def test_home_energy_unique_id():
    assert SENSOR_HOME_ENERGY in _home()._attr_unique_id


# ── Energy accumulation — battery ────────────────────────────────────────────


def test_discharge_accumulates_positive_power():
    sensor = _discharge(power_w=1000.0)
    sensor._last_update_time = time.monotonic() - 3600  # 1 h ago
    sensor._handle_coordinator_update()
    assert abs(sensor._energy_wh - 1000.0) < 1.0


def test_charge_accumulates_negative_power():
    sensor = _charge(power_w=-500.0)
    sensor._last_update_time = time.monotonic() - 3600
    sensor._handle_coordinator_update()
    assert abs(sensor._energy_wh - 500.0) < 1.0


def test_discharge_ignores_charging():
    sensor = _discharge(power_w=-300.0)
    sensor._last_update_time = time.monotonic() - 3600
    sensor._handle_coordinator_update()
    assert sensor._energy_wh == 0.0


def test_charge_ignores_discharging():
    sensor = _charge(power_w=300.0)
    sensor._last_update_time = time.monotonic() - 3600
    sensor._handle_coordinator_update()
    assert sensor._energy_wh == 0.0


# ── Energy accumulation — grid & home ────────────────────────────────────────


def test_grid_import_accumulates():
    sensor = _grid_import(power_w=2000.0)
    sensor._last_update_time = time.monotonic() - 1800  # 30 min
    sensor._handle_coordinator_update()
    assert abs(sensor._energy_wh - 1000.0) < 1.0  # 2000 W × 0.5 h


def test_grid_export_accumulates():
    sensor = _grid_export(power_w=1500.0)
    sensor._last_update_time = time.monotonic() - 3600
    sensor._handle_coordinator_update()
    assert abs(sensor._energy_wh - 1500.0) < 1.0


def test_home_energy_accumulates():
    sensor = _home(power_w=3000.0)
    sensor._last_update_time = time.monotonic() - 3600
    sensor._handle_coordinator_update()
    assert abs(sensor._energy_wh - 3000.0) < 1.0


def test_positive_sensor_ignores_zero():
    sensor = _grid_import(power_w=0.0)
    sensor._last_update_time = time.monotonic() - 3600
    sensor._handle_coordinator_update()
    assert sensor._energy_wh == 0.0


# ── General behaviour ─────────────────────────────────────────────────────────


def test_accumulation_is_additive():
    sensor = _discharge(power_w=600.0)
    for _ in range(3):
        sensor._last_update_time = time.monotonic() - 1800
        sensor._handle_coordinator_update()
    assert abs(sensor._energy_wh - 900.0) < 2.0  # 600 W × 0.5 h × 3


def test_no_accumulation_before_first_timestamp():
    sensor = _discharge(power_w=5000.0)
    assert sensor._last_update_time is None
    sensor._handle_coordinator_update()
    assert sensor._energy_wh == 0.0


def test_none_power_skipped():
    sensor = _discharge(power_w=None)
    sensor._last_update_time = time.monotonic() - 3600
    sensor._handle_coordinator_update()
    assert sensor._energy_wh == 0.0


def test_writes_ha_state_on_every_update():
    sensor = _discharge(power_w=100.0)
    sensor._last_update_time = time.monotonic() - 30
    sensor._handle_coordinator_update()
    sensor.async_write_ha_state.assert_called_once()


def test_timestamp_advances_after_update():
    sensor = _charge(power_w=-200.0)
    before = time.monotonic()
    sensor._last_update_time = before - 30
    sensor._handle_coordinator_update()
    assert sensor._last_update_time >= before


# ── RestoreSensor ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restores_previous_value():
    sensor = _discharge()
    last = MagicMock()
    last.native_value = "4321.5"
    sensor.async_get_last_sensor_data = AsyncMock(return_value=last)
    sensor.coordinator.async_add_listener = MagicMock(return_value=lambda: None)

    await sensor.async_added_to_hass()

    assert sensor._energy_wh == 4321.5
    assert sensor._last_update_time is not None


@pytest.mark.asyncio
async def test_restore_none_defaults_to_zero():
    sensor = _charge()
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)
    sensor.coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    await sensor.async_added_to_hass()
    assert sensor._energy_wh == 0.0


@pytest.mark.asyncio
async def test_restore_corrupt_value_defaults_to_zero():
    sensor = _home()
    last = MagicMock()
    last.native_value = "not-a-number"
    sensor.async_get_last_sensor_data = AsyncMock(return_value=last)
    sensor.coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    await sensor.async_added_to_hass()
    assert sensor._energy_wh == 0.0


# ── native_value ──────────────────────────────────────────────────────────────


def test_native_value_rounded_to_2dp():
    sensor = _discharge()
    sensor._energy_wh = 123.456789
    assert sensor.native_value == 123.46


def test_native_value_starts_at_zero():
    assert _charge().native_value == 0.0


# ── available ────────────────────────────────────────────────────────────────


def test_available_when_coordinator_has_data():
    assert _discharge(power_w=100.0).available is True


def test_unavailable_when_coordinator_data_is_none():
    sensor = _discharge()
    sensor.coordinator.data = None
    assert sensor.available is False
