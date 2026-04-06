"""Sensor platform for Generac PWRcell."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_HOME_ID,
    DOMAIN,
    MANUFACTURER,
    SENSOR_BATTERY_BACKUP_SECS,
    SENSOR_BATTERY_CHARGE_ENERGY,
    SENSOR_BATTERY_DISCHARGE_ENERGY,
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
from .coordinator import PWRcellCoordinator


@dataclass(frozen=True, kw_only=True)
class PWRcellSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with coordinator data key."""
    data_key: str


SENSOR_DESCRIPTIONS: tuple[PWRcellSensorDescription, ...] = (

    # ── Solar ─────────────────────────────────────────────────────────────────
    PWRcellSensorDescription(
        key="solar_power",
        data_key=SENSOR_SOLAR_POWER,
        name="Solar Production",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
    ),
    PWRcellSensorDescription(
        key="solar_energy",
        data_key=SENSOR_SOLAR_ENERGY,
        name="Solar Energy (lifetime)",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:solar-power-variant",
        suggested_display_precision=2,
    ),

    # ── Battery ───────────────────────────────────────────────────────────────
    PWRcellSensorDescription(
        key="battery_power",
        data_key=SENSOR_BATTERY_POWER,
        name="Battery Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-charging",
    ),
    PWRcellSensorDescription(
        key="battery_state_of_charge",
        data_key=SENSOR_BATTERY_SOC,
        name="Battery State of Charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
        suggested_display_precision=1,
    ),
    # Lifetime total from device — single counter, not split by direction.
    # The Energy Dashboard needs separate charge/discharge totals; those are
    # provided by PWRcellIntegratedEnergySensor below.
    PWRcellSensorDescription(
        key="battery_energy",
        data_key=SENSOR_BATTERY_ENERGY,
        name="Battery Energy (lifetime)",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:battery-arrow-up",
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    PWRcellSensorDescription(
        key="battery_temperature",
        data_key=SENSOR_BATTERY_TEMP,
        name="Battery Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    PWRcellSensorDescription(
        key="battery_voltage",
        data_key=SENSOR_BATTERY_VOLTAGE,
        name="Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sine-wave",
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),

    # ── Inverter ──────────────────────────────────────────────────────────────
    PWRcellSensorDescription(
        key="inverter_power",
        data_key=SENSOR_INVERTER_POWER,
        name="Inverter Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt-circle",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    PWRcellSensorDescription(
        key="inverter_energy",
        data_key=SENSOR_INVERTER_ENERGY,
        name="Inverter Energy (lifetime)",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    PWRcellSensorDescription(
        key="inverter_temperature",
        data_key=SENSOR_INVERTER_TEMP,
        name="Inverter Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    PWRcellSensorDescription(
        key="inverter_voltage",
        data_key=SENSOR_INVERTER_VOLTAGE,
        name="Inverter Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sine-wave",
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),

    # ── Grid ──────────────────────────────────────────────────────────────────
    # Energy sensors (grid_import_energy, grid_export_energy) are NOT listed
    # here — the API never provides lifetime grid energy totals.  They are
    # provided by PWRcellIntegratedEnergySensor instances below instead.
    PWRcellSensorDescription(
        key="grid_import_power",
        data_key=SENSOR_GRID_IMPORT_POWER,
        name="Grid Import Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-import",
    ),
    PWRcellSensorDescription(
        key="grid_export_power",
        data_key=SENSOR_GRID_EXPORT_POWER,
        name="Grid Export Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-export",
    ),

    # ── Home consumption ──────────────────────────────────────────────────────
    # home_energy is provided by PWRcellIntegratedEnergySensor below.
    PWRcellSensorDescription(
        key="home_power",
        data_key=SENSOR_HOME_POWER,
        name="Home Consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-lightning-bolt",
    ),

    # ── Net power ─────────────────────────────────────────────────────────────
    PWRcellSensorDescription(
        key="net_power",
        data_key=SENSOR_NET_POWER,
        name="Net Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
    ),

    # ── Inverter headroom ─────────────────────────────────────────────────────
    PWRcellSensorDescription(
        key="inverter_headroom",
        data_key=SENSOR_INVERTER_HEADROOM,
        name="Inverter Headroom",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),

    # ── Battery backup time ───────────────────────────────────────────────────
    PWRcellSensorDescription(
        key="battery_backup_time",
        data_key=SENSOR_BATTERY_BACKUP_SECS,
        name="Battery Backup Time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-clock",
    ),

    # ── Status / state sensors (text) ─────────────────────────────────────────
    PWRcellSensorDescription(
        key="battery_state",
        data_key=SENSOR_BATTERY_STATE,
        name="Battery State",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        icon="mdi:battery-heart-variant",
    ),
    PWRcellSensorDescription(
        key="grid_state",
        data_key=SENSOR_GRID_STATE,
        name="Grid State",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        icon="mdi:transmission-tower",
    ),
    PWRcellSensorDescription(
        key="system_mode",
        data_key=SENSOR_SYSTEM_MODE,
        name="System Mode",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        icon="mdi:cog",
    ),
)

# ── Integrated energy sensor definitions ──────────────────────────────────────
# Each tuple: (source_power_key, unique_id_suffix, name, icon, sign)
# sign = "positive" → integrate when power > 0
# sign = "negative" → integrate abs(power) when power < 0
_INTEGRATED_SENSORS: tuple[tuple[str, str, str, str, str], ...] = (
    (SENSOR_GRID_IMPORT_POWER,  SENSOR_GRID_IMPORT_ENERGY,    "Grid Import Energy",    "mdi:transmission-tower-import",  "positive"),
    (SENSOR_GRID_EXPORT_POWER,  SENSOR_GRID_EXPORT_ENERGY,    "Grid Export Energy",    "mdi:transmission-tower-export",  "positive"),
    (SENSOR_HOME_POWER,         SENSOR_HOME_ENERGY,            "Home Energy",           "mdi:home-lightning-bolt-outline", "positive"),
    (SENSOR_BATTERY_POWER,      SENSOR_BATTERY_DISCHARGE_ENERGY, "Battery Discharge Energy", "mdi:battery-arrow-up",   "positive"),
    (SENSOR_BATTERY_POWER,      SENSOR_BATTERY_CHARGE_ENERGY,  "Battery Charge Energy", "mdi:battery-arrow-down",         "negative"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Generac PWRcell sensors from a config entry."""
    coordinator: PWRcellCoordinator = hass.data[DOMAIN][entry.entry_id]
    home_id: str = entry.data.get(CONF_HOME_ID, coordinator.home_id or "unknown")

    entities: list[SensorEntity] = [
        PWRcellSensor(coordinator, description, home_id)
        for description in SENSOR_DESCRIPTIONS
    ]
    entities += [
        PWRcellIntegratedEnergySensor(
            coordinator, home_id,
            source_key=source_key,
            unique_id_suffix=uid_suffix,
            name=name,
            icon=icon,
            sign=sign,
        )
        for source_key, uid_suffix, name, icon, sign in _INTEGRATED_SENSORS
    ]
    async_add_entities(entities)


class PWRcellSensor(CoordinatorEntity[PWRcellCoordinator], SensorEntity):
    """A single Generac PWRcell sensor backed by the coordinator."""

    entity_description: PWRcellSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PWRcellCoordinator,
        description: PWRcellSensorDescription,
        home_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._home_id = home_id
        self._attr_unique_id = f"{home_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, home_id)},
            name="Generac PWRcell",
            manufacturer=MANUFACTURER,
            model="PWRcell ESS",
            serial_number=coordinator.system_serial or None,
            configuration_url="https://mypwrview.generac.com",
        )

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.entity_description.data_key)
        if value is not None and isinstance(value, float):
            if self.entity_description.native_unit_of_measurement == UnitOfPower.WATT:
                return round(value)
        return value

    @property
    def available(self) -> bool:
        if not super().available or self.coordinator.data is None:
            return False
        return self.coordinator.data.get(self.entity_description.data_key) is not None


class PWRcellIntegratedEnergySensor(CoordinatorEntity[PWRcellCoordinator], RestoreSensor):
    """Integrates a power (W) reading into a cumulative energy (kWh) total.

    Used for sensors where the Generac API provides only instantaneous power,
    not a lifetime energy counter.  Covers:

      • Grid Import Energy   — integrate grid_import_power (≥ 0 W)
      • Grid Export Energy   — integrate grid_export_power (≥ 0 W)
      • Home Energy          — integrate home_power (≥ 0 W)
      • Battery Discharge    — integrate battery_power when > 0 W
      • Battery Charge       — integrate abs(battery_power) when < 0 W

    The running total is persisted via RestoreSensor so it survives HA restarts.
    HA's long-term statistics engine records hourly/daily buckets automatically
    once the sensor appears in the Energy Dashboard.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PWRcellCoordinator,
        home_id: str,
        *,
        source_key: str,
        unique_id_suffix: str,
        name: str,
        icon: str,
        sign: str,  # "positive" | "negative"
    ) -> None:
        super().__init__(coordinator)
        self._source_key = source_key
        self._sign = sign
        self._energy_kwh: float = 0.0
        self._last_update_time: float | None = None

        self._attr_unique_id = f"{home_id}_{unique_id_suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, home_id)},
            name="Generac PWRcell",
            manufacturer=MANUFACTURER,
            model="PWRcell ESS",
        )

    async def async_added_to_hass(self) -> None:
        """Restore previous energy total and begin listening for updates."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            try:
                self._energy_kwh = float(last.native_value)
            except (TypeError, ValueError):
                self._energy_kwh = 0.0
        self._last_update_time = time.monotonic()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate power into energy on every coordinator poll."""
        now = time.monotonic()

        if self._last_update_time is not None and self.coordinator.data is not None:
            elapsed_h = (now - self._last_update_time) / 3600.0
            power_w: float | None = self.coordinator.data.get(self._source_key)

            if power_w is not None:
                if self._sign == "positive" and power_w > 0:
                    self._energy_kwh += power_w * elapsed_h / 1000.0
                elif self._sign == "negative" and power_w < 0:
                    self._energy_kwh += abs(power_w) * elapsed_h / 1000.0

        self._last_update_time = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._energy_kwh, 2)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
