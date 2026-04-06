"""DataUpdateCoordinator for Generac PWRcell.

Primary data source: GET /live/v1/homes  (schema confirmed from live API)
  - Returns home metadata, tariff info, and per-device status for every
    device in the system (PVL optimizers, INVERTER, BATTERY, BEACON).
  - Auth: Bearer <id_token>

Secondary data source: GET /live/v2/homes/{homeId}/telemetry  (schema TBC)
  - Returns aggregate power-flow data (home consumption, grid import/export).
  - Will be wired in once the response schema is confirmed from mitmweb.
  - Auth: Bearer <id_token>

Device type → sensor mapping (from live /live/v1/homes response):
  PVL      → solar production  (sum powerInWatts, sum lifeTimeEnergyInWh)
  BATTERY  → battery power, SOC, temperature, voltage, lifetime energy
  INVERTER → inverter power, temperature, voltage, lifetime energy
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .auth import AuthError, GeneracAuth
from .const import (
    DEFAULT_API_BASE,
    DEVICE_TYPE_BATTERY,
    DEVICE_TYPE_INVERTER,
    DEVICE_TYPE_PVL,
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
    SENSOR_BATTERY_BACKUP_SECS,
    SENSOR_BATTERY_ENERGY,
    SENSOR_BATTERY_POWER,
    SENSOR_BATTERY_SOC,
    SENSOR_BATTERY_STATE,
    SENSOR_BATTERY_TEMP,
    SENSOR_BATTERY_VOLTAGE,
    SENSOR_GRID_EXPORT_ENERGY,
    SENSOR_GRID_EXPORT_POWER,
    SENSOR_GRID_IMPORT_ENERGY,
    SENSOR_GRID_IMPORT_POWER,
    SENSOR_GRID_STATE,
    SENSOR_HOME_ENERGY,
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

_LOGGER = logging.getLogger(__name__)

_TELEMETRY_LOOKBACK_SECONDS = 90


class PWRcellCoordinator(DataUpdateCoordinator):
    """Polls the Generac cloud API every 30 s and normalises device data."""

    def __init__(
        self,
        hass: HomeAssistant,
        auth: GeneracAuth,
        user_id: str,
        home_id: str | None = None,
        api_base: str = DEFAULT_API_BASE,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.auth = auth
        self.user_id = user_id
        self._home_id: str | None = home_id

        # Build data URLs from api_base so a local mock server can be used.
        self._homes_url = f"{api_base}/live/v1/homes"
        self._telemetry_url_template = f"{api_base}/live/v2/homes/{{home_id}}/telemetry"

        # Expose home metadata for device registry
        self.home_address: str = ""
        self.home_timezone: str = ""
        self.system_serial: str = ""

    @property
    def home_id(self) -> str | None:
        return self._home_id

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch homes data and optional telemetry; return merged sensor values."""
        try:
            homes_raw = await self.auth.async_get(self._homes_url, use_id_token=True)
        except AuthError as exc:
            raise UpdateFailed(f"Generac PWRcell homes fetch failed: {exc}") from exc

        if not homes_raw:
            raise UpdateFailed("Generac API returned empty homes list.")

        home = homes_raw[0]
        self._home_id = home.get("homeId", self._home_id)
        self.home_address = _fmt_address(home)
        self.home_timezone = home.get("timezone", "")
        self.system_serial = _first_system_serial(home)

        result = _parse_homes(home)

        # --- Telemetry (aggregate power flow) ---
        # Schema is TBC; skip gracefully if it fails so the rest still works.
        if self._home_id:
            try:
                telemetry_raw = await self._async_fetch_telemetry()
                if telemetry_raw:
                    result.update(_parse_telemetry(telemetry_raw))
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Telemetry fetch skipped (schema TBC or error): %s", exc
                )

        return result

    async def _async_fetch_telemetry(self) -> Any:
        url = self._telemetry_url_template.format(home_id=self._home_id)
        from_iso = (
            datetime.now(timezone.utc) - timedelta(seconds=_TELEMETRY_LOOKBACK_SECONDS)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self.auth.async_get(
            url, params={"fromIso": from_iso}, use_id_token=True
        )


# ── Homes parsing (confirmed schema) ──────────────────────────────────────────


def _parse_homes(home: dict) -> dict[str, Any]:
    """Extract all sensor values from a single home object.

    Confirmed field paths from live /live/v1/homes response:
      home.systems[].systemDevices[].deviceType
      home.systems[].systemDevices[].deviceStatus.powerInWatts
      home.systems[].systemDevices[].deviceStatus.lifeTimeEnergyInWh
      home.systems[].systemDevices[].deviceStatus.soc         (BATTERY only)
      home.systems[].systemDevices[].deviceStatus.temperatureInCelsius
      home.systems[].systemDevices[].deviceStatus.voltage
    """
    # Index all devices by type
    pvl_devices:      list[dict] = []
    battery_status:   dict       = {}
    inverter_status:  dict       = {}

    for system in home.get("systems", []):
        for device in system.get("systemDevices", []):
            dtype  = device.get("deviceType", "")
            status = device.get("deviceStatus", {})
            if dtype == DEVICE_TYPE_PVL:
                pvl_devices.append(status)
            elif dtype == DEVICE_TYPE_BATTERY and not battery_status:
                battery_status = status
            elif dtype == DEVICE_TYPE_INVERTER and not inverter_status:
                inverter_status = status

    # ── Solar (sum across all PVL optimizers) ─────────────────────────────────
    solar_w   = float(sum(d.get("powerInWatts", 0) for d in pvl_devices))
    solar_kwh = float(sum(d.get("lifeTimeEnergyInWh", 0) for d in pvl_devices)) / 1000.0

    # ── Battery ───────────────────────────────────────────────────────────────
    batt_w       = _f(battery_status, "powerInWatts")
    batt_soc     = _f(battery_status, "soc")
    _batt_wh     = _f(battery_status, "lifeTimeEnergyInWh")
    batt_kwh     = _batt_wh / 1000.0 if _batt_wh is not None else None
    batt_temp    = _f(battery_status, "temperatureInCelsius")
    batt_voltage = _f(battery_status, "voltage")

    # ── Inverter ──────────────────────────────────────────────────────────────
    inv_w        = _f(inverter_status, "powerInWatts")
    _inv_wh      = _f(inverter_status, "lifeTimeEnergyInWh")
    inv_kwh      = _inv_wh / 1000.0 if _inv_wh is not None else None
    inv_temp     = _f(inverter_status, "temperatureInCelsius")
    inv_voltage  = _f(inverter_status, "voltage")

    return {
        # Solar
        SENSOR_SOLAR_POWER:    solar_w,
        SENSOR_SOLAR_ENERGY:   solar_kwh,
        # Battery
        SENSOR_BATTERY_POWER:   batt_w,
        SENSOR_BATTERY_SOC:     batt_soc,
        SENSOR_BATTERY_ENERGY:  batt_kwh,
        SENSOR_BATTERY_TEMP:    batt_temp,
        SENSOR_BATTERY_VOLTAGE: batt_voltage,
        # Inverter
        SENSOR_INVERTER_POWER:   inv_w,
        SENSOR_INVERTER_ENERGY:  inv_kwh,
        SENSOR_INVERTER_TEMP:    inv_temp,
        SENSOR_INVERTER_VOLTAGE: inv_voltage,
        # Grid / consumption / status — filled in by telemetry
        SENSOR_HOME_POWER:          None,
        SENSOR_HOME_ENERGY:         None,
        SENSOR_GRID_IMPORT_POWER:   None,
        SENSOR_GRID_IMPORT_ENERGY:  None,
        SENSOR_GRID_EXPORT_POWER:   None,
        SENSOR_GRID_EXPORT_ENERGY:  None,
        SENSOR_NET_POWER:           None,
        SENSOR_BATTERY_STATE:       None,
        SENSOR_BATTERY_BACKUP_SECS: None,
        SENSOR_GRID_STATE:          None,
        SENSOR_SYSTEM_MODE:         None,
        SENSOR_INVERTER_HEADROOM:   None,
    }


# ── Telemetry parsing (confirmed schema from live API) ────────────────────────


def _parse_telemetry(raw: Any) -> dict[str, Any]:
    """Extract aggregate power-flow data from the telemetry endpoint.

    Confirmed response schema (GET /live/v2/homes/{homeId}/telemetry):
      Returns a list of per-second snapshots; we use the last entry.
      Returns [] when no new data since fromIso — caller handles this.

      Each entry:
        date                          Unix timestamp string
        solar.powerKw                 Solar production (kW)
        grid.powerKw                  Grid power (+ve = import, -ve = export)
        consumption.powerKw           Home consumption (kW)
        generator.powerKw             Generator power (kW)
        battery.powerKw               Battery power (+ve = discharging)
        battery.soC                   State of charge 0-100  ← capital C!
        battery.batteryBackupTimeInSeconds
        battery.batteryState          e.g. "BATTERY_SOC_STATUS_UNSPECIFIED"
        system.{systemId}.gridState   e.g. "GRID_CONNECTED"
        system.{systemId}.sysMode     e.g. "SELF_SUPPLY"
        system.{systemId}.inverterHeadRoomKw

    All power values are in kW — converted to W (×1000) for HA sensors.
    """
    # Response is a list of second-by-second snapshots; use the last one
    if not isinstance(raw, list) or not raw:
        return {}
    entry = raw[-1]
    if not isinstance(entry, dict):
        return {}

    _LOGGER.debug("Telemetry entry: %s", entry)

    def _kw_to_w(section: str, field: str = "powerKw") -> float | None:
        sec = entry.get(section, {})
        if not isinstance(sec, dict):
            return None
        v = sec.get(field)
        return round(float(v) * 1000) if v is not None else None

    def _val(section: str, field: str) -> Any:
        sec = entry.get(section, {})
        return sec.get(field) if isinstance(sec, dict) else None

    # Power (W) — all converted from kW
    solar_w   = _kw_to_w("solar")
    grid_w    = _kw_to_w("grid")       # positive = import, negative = export
    home_w    = _kw_to_w("consumption")
    batt_w    = _kw_to_w("battery")

    grid_import_w = max(grid_w, 0)  if grid_w is not None else None
    grid_export_w = abs(min(grid_w, 0)) if grid_w is not None else None

    # Battery details
    batt_soc          = _val("battery", "soC")           # note capital C
    batt_backup_secs  = _val("battery", "batteryBackupTimeInSeconds")
    batt_state        = _val("battery", "batteryState")  # e.g. "BATTERY_SOC_STATUS_UNSPECIFIED"

    if batt_soc is not None:
        batt_soc = float(batt_soc)
    if batt_backup_secs is not None:
        batt_backup_secs = int(batt_backup_secs)

    # System-level state (first system found)
    grid_state:    str | None = None
    sys_mode:      str | None = None
    inv_headroom_w: float | None = None

    system_map = entry.get("system", {})
    if isinstance(system_map, dict):
        for sys_data in system_map.values():
            if not isinstance(sys_data, dict):
                continue
            grid_state    = sys_data.get("gridState")
            sys_mode      = sys_data.get("sysMode")
            hrw = sys_data.get("inverterHeadRoomKw")
            if hrw is not None:
                inv_headroom_w = round(float(hrw) * 1000)
            break  # only one system per home

    updates: dict[str, Any] = {}

    # Power sensors — telemetry is authoritative for aggregate flow
    for key, val in [
        (SENSOR_SOLAR_POWER,       solar_w),
        (SENSOR_HOME_POWER,        home_w),
        (SENSOR_NET_POWER,         grid_w),
        (SENSOR_GRID_IMPORT_POWER, grid_import_w),
        (SENSOR_GRID_EXPORT_POWER, grid_export_w),
        (SENSOR_BATTERY_POWER,     batt_w),
        # SOC from telemetry is fresher than homes (telemetry updates per-second)
        (SENSOR_BATTERY_SOC,       batt_soc),
        # Status / state sensors
        (SENSOR_BATTERY_STATE,       batt_state),
        (SENSOR_BATTERY_BACKUP_SECS, batt_backup_secs),
        (SENSOR_GRID_STATE,          grid_state),
        (SENSOR_SYSTEM_MODE,         sys_mode),
        (SENSOR_INVERTER_HEADROOM,   inv_headroom_w),
    ]:
        if val is not None:
            updates[key] = val

    return updates


# ── Helpers ───────────────────────────────────────────────────────────────────


def _f(d: dict, key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_address(home: dict) -> str:
    parts = [home.get("address1", ""), home.get("city", ""), home.get("state", "")]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _first_system_serial(home: dict) -> str:
    for system in home.get("systems", []):
        serial = system.get("serialNumber", "")
        if serial:
            return serial
    return ""
