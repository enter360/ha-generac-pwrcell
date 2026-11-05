"""Unit tests for PWRcellIntegratedEnergySensor (a view of the coordinator's totals)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.generac_pwrcell.const import (
    SENSOR_BATTERY_CHARGE_ENERGY,
    SENSOR_BATTERY_DISCHARGE_ENERGY,
    SENSOR_GRID_EXPORT_ENERGY,
    SENSOR_GRID_IMPORT_ENERGY,
    SENSOR_HOME_ENERGY,
)
from custom_components.generac_pwrcell.coordinator import PWRcellCoordinator
from custom_components.generac_pwrcell.sensor import (
    _INTEGRATED_SENSORS,
    PWRcellIntegratedEnergySensor,
)

HOME_ID = "home-test-001"


def _sensor(key=SENSOR_BATTERY_DISCHARGE_ENERGY) -> PWRcellIntegratedEnergySensor:
    coord = PWRcellCoordinator(MagicMock(), None, AsyncMock(), "user-1")
    coord.data = {}
    sensor = PWRcellIntegratedEnergySensor.__new__(PWRcellIntegratedEnergySensor)  # pylint: disable=no-value-for-parameter
    sensor.coordinator = coord
    sensor._key = key
    sensor._attr_unique_id = f"{HOME_ID}_{key}"
    return sensor


def test_one_sensor_per_counter_with_distinct_unique_ids():
    keys = [k for k, _, _ in _INTEGRATED_SENSORS]
    assert sorted(keys) == sorted([
        SENSOR_GRID_IMPORT_ENERGY, SENSOR_GRID_EXPORT_ENERGY, SENSOR_HOME_ENERGY,
        SENSOR_BATTERY_CHARGE_ENERGY, SENSOR_BATTERY_DISCHARGE_ENERGY,
    ])
    assert len(set(keys)) == len(keys)


def test_native_value_reads_coordinator_and_rounds():
    sensor = _sensor()
    sensor.coordinator.energy_kwh[SENSOR_BATTERY_DISCHARGE_ENERGY] = 123.456789
    assert sensor.native_value == 123.46


def test_native_value_starts_at_zero():
    assert _sensor(SENSOR_BATTERY_CHARGE_ENERGY).native_value == 0.0


@pytest.mark.asyncio
async def test_restores_previous_value_into_coordinator():
    sensor = _sensor()
    last = MagicMock()
    last.native_value = "4321.5"
    sensor.async_get_last_sensor_data = AsyncMock(return_value=last)
    await sensor.async_added_to_hass()
    assert sensor.native_value == 4321.5


@pytest.mark.asyncio
async def test_restore_adds_to_what_first_poll_already_counted():
    sensor = _sensor()
    sensor.coordinator.energy_kwh[SENSOR_BATTERY_DISCHARGE_ENERGY] = 0.25
    last = MagicMock()
    last.native_value = "10"
    sensor.async_get_last_sensor_data = AsyncMock(return_value=last)
    await sensor.async_added_to_hass()
    assert sensor.native_value == 10.25


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [None, "not-a-number"])
async def test_restore_nothing_usable_starts_from_zero(saved):
    sensor = _sensor()
    last = None
    if saved is not None:
        last = MagicMock()
        last.native_value = saved
    sensor.async_get_last_sensor_data = AsyncMock(return_value=last)
    await sensor.async_added_to_hass()
    assert sensor.native_value == 0.0


def test_available_when_coordinator_has_data():
    assert _sensor().available is True


def test_unavailable_when_coordinator_data_is_none():
    sensor = _sensor()
    sensor.coordinator.data = None
    assert sensor.available is False
