"""Constants for the Generac PWRcell integration."""

DOMAIN = "generac_pwrcell"
MANUFACTURER = "Generac"

# ── App identity ───────────────────────────────────────────────────────────────
# Credentials extracted from the Generac PWRcell mobile app (com.neurio.generachome)
# by intercepting its HTTPS traffic.  These identify the mobile client to the
# Generac cloud — they are NOT the end-user's credentials.
APP_CLIENT_ID     = "1im6pfcmq8oo8db7usd8kjrgkk"
APP_CLIENT_SECRET = "bpbuhh5u8atmuekq4rh4l8bhnig5cqd2el66tkfmp60gs3sd62f"
APP_VERSION       = "1.30.0"
APP_BUILD         = "38904"
APP_USER_AGENT    = f"GeneracHome/{APP_BUILD} CFNetwork/3860.400.51 Darwin/25.3.0"

# ── API base ───────────────────────────────────────────────────────────────────
DEFAULT_API_BASE = "https://generac-api.neur.io"

# Kept for backwards-compat; production callers should use DEFAULT_API_BASE.
API_BASE = DEFAULT_API_BASE

# Auth  (discovered from app traffic intercept)
SIGNIN_URL         = f"{DEFAULT_API_BASE}/sessions/v1/signin"
TOKEN_REFRESH_URL  = f"{DEFAULT_API_BASE}/sessions/v2/refresh/token"

# Homes endpoint — confirmed schema from live API capture
# Returns: list of home objects with nested systems → systemDevices
# Auth:    Bearer <id_token>
HOMES_URL = f"{DEFAULT_API_BASE}/live/v1/homes"

# Telemetry endpoint — confirmed URL, schema TBC (awaiting response capture)
# Auth:    Bearer <id_token>
# Param:   fromIso=<ISO8601 timestamp>
TELEMETRY_URL_TEMPLATE = f"{DEFAULT_API_BASE}/live/v2/homes/{{home_id}}/telemetry"

# ── Config entry keys ──────────────────────────────────────────────────────────
CONF_USER_ID = "user_id"
CONF_HOME_ID = "home_id"
# Optional override — set to a local mock server URL for development/testing
CONF_API_BASE = "api_base"

# ── Polling ────────────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS = 30

# ── Device types (from systemDevices[].deviceType) ────────────────────────────
DEVICE_TYPE_PVL      = "PVL"       # Power Link — solar string optimizer
DEVICE_TYPE_INVERTER = "INVERTER"  # Main grid-tie inverter
DEVICE_TYPE_BATTERY  = "BATTERY"   # PWRcell battery module
DEVICE_TYPE_BEACON   = "BEACON"    # Communications/control module

# ── Sensor unique ID suffixes ──────────────────────────────────────────────────
# Solar (aggregate across all PVL devices)
SENSOR_SOLAR_POWER          = "solar_power"
SENSOR_SOLAR_ENERGY         = "solar_energy"

# Grid / consumption — from telemetry endpoint (schema TBC)
SENSOR_GRID_IMPORT_POWER    = "grid_import_power"
SENSOR_GRID_IMPORT_ENERGY   = "grid_import_energy"
SENSOR_GRID_EXPORT_POWER    = "grid_export_power"
SENSOR_GRID_EXPORT_ENERGY   = "grid_export_energy"
SENSOR_HOME_POWER           = "home_power"
SENSOR_HOME_ENERGY          = "home_energy"
SENSOR_NET_POWER            = "net_power"

# Battery — from homes → systemDevices (BATTERY)
SENSOR_BATTERY_POWER            = "battery_power"
SENSOR_BATTERY_SOC              = "battery_state_of_charge"
SENSOR_BATTERY_ENERGY           = "battery_energy"
SENSOR_BATTERY_TEMP             = "battery_temperature"
SENSOR_BATTERY_VOLTAGE          = "battery_voltage"
# Derived energy totals (integrated from battery_power in the sensor layer)
# Separate charge / discharge counters required by the HA Energy Dashboard.
SENSOR_BATTERY_CHARGE_ENERGY    = "battery_charge_energy"
SENSOR_BATTERY_DISCHARGE_ENERGY = "battery_discharge_energy"

# Inverter — from homes → systemDevices (INVERTER)
SENSOR_INVERTER_POWER       = "inverter_power"
SENSOR_INVERTER_ENERGY      = "inverter_energy"
SENSOR_INVERTER_TEMP        = "inverter_temperature"
SENSOR_INVERTER_VOLTAGE     = "inverter_voltage"
SENSOR_INVERTER_HEADROOM    = "inverter_headroom"

# Status / state sensors — from telemetry response (confirmed schema)
# battery.batteryState  e.g. "BATTERY_SOC_STATUS_UNSPECIFIED", "BATTERY_SOC_STATUS_LOW", …
# system.{id}.gridState e.g. "GRID_CONNECTED", "GRID_DISCONNECTED"
# system.{id}.sysMode   e.g. "SELF_SUPPLY", "CLEAN_BACKUP", "PRIORITY_BACKUP"
SENSOR_BATTERY_STATE        = "battery_state"
SENSOR_BATTERY_BACKUP_SECS  = "battery_backup_time"
SENSOR_GRID_STATE           = "grid_state"
SENSOR_SYSTEM_MODE          = "system_mode"
