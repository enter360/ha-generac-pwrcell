"""Unit tests for PWRcellCoordinator and its parsing helpers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.generac_pwrcell.const import (
    DEFAULT_API_BASE,
    SENSOR_BATTERY_BACKUP_SECS,
    SENSOR_BATTERY_ENERGY,
    SENSOR_BATTERY_POWER,
    SENSOR_BATTERY_SOC,
    SENSOR_BATTERY_STATE,
    SENSOR_BATTERY_TEMP,
    SENSOR_BATTERY_VOLTAGE,
    SENSOR_GRID_EXPORT_POWER,
    SENSOR_GRID_IMPORT_POWER,
    SENSOR_GRID_STATE,
    SENSOR_HOME_POWER,
    SENSOR_INVERTER_ENERGY,
    SENSOR_INVERTER_HEADROOM,
    SENSOR_INVERTER_POWER,
    SENSOR_INVERTER_TEMP,
    SENSOR_INVERTER_VOLTAGE,
    SENSOR_NET_POWER,
    SENSOR_SOLAR_ENERGY,
    SENSOR_SOLAR_POWER,
    SENSOR_SYSTEM_MODE,
)
from custom_components.generac_pwrcell.coordinator import (
    PWRcellCoordinator,
    _fmt_address,
    _parse_homes,
    _parse_telemetry,
)

MOCK_BASE = "http://localhost:8080"


# ── _parse_homes ──────────────────────────────────────────────────────────────


def test_parse_homes_solar_aggregated(homes_response):
    home = homes_response[0]
    result = _parse_homes(home)

    # Two PVL devices: 2500 + 1800 = 4300 W
    assert result[SENSOR_SOLAR_POWER] == 4300.0
    # Lifetime energy: 12_000_000 + 9_500_000 = 21_500_000 Wh → 21_500 kWh
    assert result[SENSOR_SOLAR_ENERGY] == 21_500.0


def test_parse_homes_battery(homes_response):
    result = _parse_homes(homes_response[0])

    assert result[SENSOR_BATTERY_POWER] == -500.0
    assert result[SENSOR_BATTERY_SOC] == 85.0
    assert result[SENSOR_BATTERY_ENERGY] == 5_000.0  # 5_000_000 Wh → 5_000 kWh
    assert result[SENSOR_BATTERY_TEMP] == 25.0
    assert result[SENSOR_BATTERY_VOLTAGE] == 48.0


def test_parse_homes_inverter(homes_response):
    result = _parse_homes(homes_response[0])

    assert result[SENSOR_INVERTER_POWER] == 3800.0
    assert result[SENSOR_INVERTER_ENERGY] == 18_000.0  # 18_000_000 Wh → 18_000 kWh
    assert result[SENSOR_INVERTER_TEMP] == 35.0
    assert result[SENSOR_INVERTER_VOLTAGE] == 240.0


def test_parse_homes_telemetry_fields_are_none(homes_response):
    """Fields filled only by telemetry must be None after homes-only parsing."""
    result = _parse_homes(homes_response[0])

    assert result[SENSOR_HOME_POWER] is None
    assert result[SENSOR_GRID_IMPORT_POWER] is None
    assert result[SENSOR_GRID_EXPORT_POWER] is None
    assert result[SENSOR_NET_POWER] is None
    assert result[SENSOR_BATTERY_STATE] is None
    assert result[SENSOR_GRID_STATE] is None
    assert result[SENSOR_SYSTEM_MODE] is None
    assert result[SENSOR_INVERTER_HEADROOM] is None


def test_parse_homes_no_devices():
    home = {"homeId": "x", "systems": []}
    result = _parse_homes(home)

    assert result[SENSOR_SOLAR_POWER] == 0.0
    assert result[SENSOR_BATTERY_POWER] is None
    assert result[SENSOR_INVERTER_POWER] is None


def test_parse_homes_missing_fields():
    """Devices with missing status keys should yield None, not KeyError."""
    home = {
        "homeId": "x",
        "systems": [
            {
                "serialNumber": "S1",
                "systemDevices": [
                    {"deviceType": "BATTERY", "deviceStatus": {}},
                    {"deviceType": "INVERTER", "deviceStatus": {}},
                ],
            }
        ],
    }
    result = _parse_homes(home)
    assert result[SENSOR_BATTERY_POWER] is None
    assert result[SENSOR_BATTERY_SOC] is None
    assert result[SENSOR_INVERTER_POWER] is None


# ── _parse_telemetry ──────────────────────────────────────────────────────────


def test_parse_telemetry_uses_last_entry(telemetry_response):
    result = _parse_telemetry(telemetry_response)

    # Last entry: solar 4.3 kW → 4300 W
    assert result[SENSOR_SOLAR_POWER] == 4300
    # Last entry: consumption 2.8 kW → 2800 W
    assert result[SENSOR_HOME_POWER] == 2800
    # Last entry: battery SOC 85.0
    assert result[SENSOR_BATTERY_SOC] == 85.0


def test_parse_telemetry_grid_import_export(telemetry_response):
    result = _parse_telemetry(telemetry_response)

    # grid.powerKw = -1.5 → export 1500 W, import 0 W
    assert result[SENSOR_GRID_EXPORT_POWER] == 1500
    assert result[SENSOR_GRID_IMPORT_POWER] == 0


def test_parse_telemetry_grid_import():
    raw = [{"grid": {"powerKw": 2.0}, "consumption": {"powerKw": 2.0},
            "solar": {"powerKw": 0.0}, "battery": {}, "system": {}}]
    result = _parse_telemetry(raw)

    assert result[SENSOR_GRID_IMPORT_POWER] == 2000
    assert result[SENSOR_GRID_EXPORT_POWER] == 0


def test_parse_telemetry_system_state(telemetry_response):
    result = _parse_telemetry(telemetry_response)

    assert result[SENSOR_GRID_STATE] == "GRID_CONNECTED"
    assert result[SENSOR_SYSTEM_MODE] == "SELF_SUPPLY"
    assert result[SENSOR_INVERTER_HEADROOM] == 1200  # 1.2 kW → 1200 W


def test_parse_telemetry_battery_state(telemetry_response):
    result = _parse_telemetry(telemetry_response)

    assert result[SENSOR_BATTERY_STATE] == "BATTERY_SOC_STATUS_NOMINAL"
    assert result[SENSOR_BATTERY_BACKUP_SECS] == 15000


def test_parse_telemetry_empty_list():
    assert _parse_telemetry([]) == {}


def test_parse_telemetry_not_a_list():
    assert _parse_telemetry(None) == {}
    assert _parse_telemetry({}) == {}


def test_parse_telemetry_entry_not_dict():
    assert _parse_telemetry(["not-a-dict"]) == {}


def test_parse_telemetry_missing_sections():
    raw = [{"date": "12345"}]
    result = _parse_telemetry(raw)
    # Should return an empty dict (all sections missing → all None → nothing added)
    assert isinstance(result, dict)


# ── _fmt_address ──────────────────────────────────────────────────────────────


def test_fmt_address_full():
    home = {"address1": "123 Main St", "city": "Springfield", "state": "IL"}
    assert _fmt_address(home) == "123 Main St, Springfield, IL"


def test_fmt_address_partial():
    home = {"address1": "", "city": "Chicago", "state": "IL"}
    assert _fmt_address(home) == "Chicago, IL"


def test_fmt_address_empty():
    assert _fmt_address({}) == ""


# ── PWRcellCoordinator URL derivation ─────────────────────────────────────────


def test_coordinator_urls_use_custom_base():
    hass = MagicMock()
    auth = MagicMock()
    coord = PWRcellCoordinator(hass, auth, "user-1", api_base=MOCK_BASE)

    assert coord._homes_url == f"{MOCK_BASE}/live/v1/homes"
    assert "live/v2/homes" in coord._telemetry_url_template
    assert coord._telemetry_url_template.startswith(MOCK_BASE)


def test_coordinator_urls_default_to_production():
    hass = MagicMock()
    auth = MagicMock()
    coord = PWRcellCoordinator(hass, auth, "user-1")

    assert coord._homes_url.startswith(DEFAULT_API_BASE)
    assert coord._telemetry_url_template.startswith(DEFAULT_API_BASE)


# ── PWRcellCoordinator._async_update_data ─────────────────────────────────────


@pytest.mark.asyncio
async def test_async_update_data_merges_homes_and_telemetry(homes_response, telemetry_response):
    hass = MagicMock()
    auth = AsyncMock()
    auth.async_get = AsyncMock(side_effect=[homes_response, telemetry_response])

    coord = PWRcellCoordinator(hass, auth, "user-1", api_base=MOCK_BASE)
    result = await coord._async_update_data()

    # From homes: solar sum
    assert result[SENSOR_SOLAR_POWER] == 4300  # telemetry overrides with 4300 W
    # From telemetry: home consumption
    assert result[SENSOR_HOME_POWER] == 2800
    assert result[SENSOR_GRID_STATE] == "GRID_CONNECTED"


@pytest.mark.asyncio
async def test_async_update_data_telemetry_failure_is_graceful(homes_response):
    """If telemetry fetch fails, homes data is still returned."""
    hass = MagicMock()
    auth = AsyncMock()
    auth.async_get = AsyncMock(side_effect=[homes_response, Exception("timeout")])

    coord = PWRcellCoordinator(hass, auth, "user-1", api_base=MOCK_BASE)
    result = await coord._async_update_data()

    # Homes data intact
    assert result[SENSOR_SOLAR_POWER] == 4300.0
    assert result[SENSOR_BATTERY_SOC] == 85.0
    # Telemetry fields remain None
    assert result[SENSOR_HOME_POWER] is None


@pytest.mark.asyncio
async def test_async_update_data_empty_homes_raises():
    from custom_components.generac_pwrcell.auth import AuthError
    from homeassistant.helpers.update_coordinator import UpdateFailed

    hass = MagicMock()
    auth = AsyncMock()
    auth.async_get = AsyncMock(return_value=[])

    coord = PWRcellCoordinator(hass, auth, "user-1", api_base=MOCK_BASE)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_async_update_data_auth_error_raises(monkeypatch):
    from custom_components.generac_pwrcell.auth import AuthError
    from homeassistant.helpers.update_coordinator import UpdateFailed

    hass = MagicMock()
    auth = AsyncMock()
    auth.async_get = AsyncMock(side_effect=AuthError("bad token"))

    coord = PWRcellCoordinator(hass, auth, "user-1", api_base=MOCK_BASE)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


# ── Monotonic guard (solar lifetime energy) ───────────────────────────────────


def _homes_with_solar(solar_wh: float) -> list[dict]:
    """Minimal homes response with a single PVL device at the given lifetime Wh."""
    return [
        {
            "homeId": "home-1",
            "systems": [
                {
                    "serialNumber": "S1",
                    "systemDevices": [
                        {
                            "deviceType": "PVL",
                            "deviceStatus": {
                                "powerInWatts": 1000.0,
                                "lifeTimeEnergyInWh": solar_wh,
                            },
                        }
                    ],
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_solar_monotonic_guard_rejects_decrease(caplog):
    """A lower API reading must be discarded; the previous value is preserved."""
    import logging

    hass = MagicMock()
    auth = AsyncMock()

    coord = PWRcellCoordinator(hass, auth, "user-1", api_base=MOCK_BASE)
    coord._last_solar_wh = 30_000_000.0  # simulate previously seen high value

    auth.async_get = AsyncMock(return_value=_homes_with_solar(16_000_000.0))

    with caplog.at_level(logging.WARNING, logger="custom_components.generac_pwrcell.coordinator"):
        result = await coord._async_update_data()

    assert result[SENSOR_SOLAR_ENERGY] == 30_000_000.0
    assert coord._last_solar_wh == 30_000_000.0
    assert "Solar lifetime energy decreased" in caplog.text


@pytest.mark.asyncio
async def test_solar_monotonic_guard_accepts_increase():
    """A higher API reading must be accepted and the high-water mark updated."""
    hass = MagicMock()
    auth = AsyncMock()

    coord = PWRcellCoordinator(hass, auth, "user-1", api_base=MOCK_BASE)
    coord._last_solar_wh = 30_000_000.0

    auth.async_get = AsyncMock(return_value=_homes_with_solar(30_100_000.0))

    result = await coord._async_update_data()

    assert result[SENSOR_SOLAR_ENERGY] == 30_100_000.0
    assert coord._last_solar_wh == 30_100_000.0


@pytest.mark.asyncio
async def test_solar_monotonic_guard_accepts_equal():
    """An equal API reading (no new production) must pass through unchanged."""
    hass = MagicMock()
    auth = AsyncMock()

    coord = PWRcellCoordinator(hass, auth, "user-1", api_base=MOCK_BASE)
    coord._last_solar_wh = 30_000_000.0

    auth.async_get = AsyncMock(return_value=_homes_with_solar(30_000_000.0))

    result = await coord._async_update_data()

    assert result[SENSOR_SOLAR_ENERGY] == 30_000_000.0
