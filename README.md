# Generac PWRcell — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2023.1%2B-blue)](https://www.home-assistant.io/)

A Home Assistant custom integration for the **Generac PWRcell** solar + battery system. Pulls live data from the Generac cloud API using the same endpoints as the official PWRcell mobile app.

No local access required — the PWRview monitoring unit (a Raspberry Pi) locks down all inbound network connections, so this integration uses the Generac cloud API over HTTPS.

---

## Features

**24 sensors across two confirmed API endpoints:**

### Power & Energy (live, 30-second polling)
| Sensor | Unit | Notes |
|--------|------|-------|
| Solar Production | W | Aggregate across all PVL optimizers |
| Home Consumption | W | Total home load |
| Grid Import Power | W | Power drawn from utility |
| Grid Export Power | W | Power sent to utility |
| Net Power | W | Grid power (+ve import / −ve export) |
| Battery Power | W | +ve discharging / −ve charging |
| Inverter Power | W | |

### Battery
| Sensor | Unit | Notes |
|--------|------|-------|
| Battery State of Charge | % | Updated per-second from telemetry |
| Battery Temperature | °C | |
| Battery Voltage | V | |
| Battery State | text | e.g. `BATTERY_SOC_STATUS_LOW` |
| Battery Backup Time | s | Estimated backup time remaining |

### Lifetime Energy (for HA Energy Dashboard)
| Sensor | Unit | Notes |
|--------|------|-------|
| Solar Energy (lifetime) | Wh | Sum of all PVL lifetime production |
| Battery Energy (lifetime) | Wh | |
| Inverter Energy (lifetime) | Wh | |
| Grid Import Energy (lifetime) | Wh | From telemetry |
| Grid Export Energy (lifetime) | Wh | From telemetry |
| Home Energy (lifetime) | Wh | From telemetry |

### System Status
| Sensor | Notes |
|--------|-------|
| Grid State | e.g. `GRID_CONNECTED`, `GRID_DISCONNECTED` |
| System Mode | e.g. `SELF_SUPPLY`, `CLEAN_BACKUP`, `PRIORITY_BACKUP` |
| Inverter Temperature | °C |
| Inverter Headroom | W — available inverter capacity |

---

## Requirements

- Home Assistant 2023.1 or later
- A Generac PWRcell system with PWRview monitoring
- A Generac account (the same email + password you use in the PWRcell mobile app)
- Internet access from your HA instance

---

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/enter360/ha-generac-pwrcell` as an **Integration**
3. Search for "Generac PWRcell" and install
4. Restart Home Assistant

### Manual

1. Download or clone this repository
2. Copy the `custom_components/generac_pwrcell/` folder into your HA config directory:
   ```
   config/
   └── custom_components/
       └── generac_pwrcell/
           ├── __init__.py
           ├── auth.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── manifest.json
           ├── sensor.py
           └── strings.json
   ```
3. Restart Home Assistant

---

## Configuration

1. Go to **Settings → Integrations → Add Integration**
2. Search for **Generac PWRcell**
3. Enter your Generac account **email** and **password** (same credentials as the PWRcell mobile app)
4. Click Submit — the integration will sign in, discover your system, and start polling

That's it. No API keys, no developer portal registration required.

---

## Home Assistant Energy Dashboard

The integration exposes `TOTAL_INCREASING` lifetime energy sensors suitable for the HA Energy Dashboard. To configure:

1. Go to **Settings → Dashboards → Energy**
2. Add sources:
   - **Solar panels** → `Solar Energy (lifetime)`
   - **Grid consumption** → `Grid Import Energy (lifetime)`
   - **Return to grid** → `Grid Export Energy (lifetime)`
   - **Battery** → `Battery Energy (lifetime)` (charge) + `Battery Energy (lifetime)` (discharge)

---

## API Details

This integration communicates with `generac-api.neur.io` — the same backend used by the official Generac PWRcell mobile app (`com.neurio.generachome`). Two endpoints are used:

| Endpoint | Purpose | Auth |
|----------|---------|------|
| `POST /sessions/v1/signin` | Sign in with email + password | Basic (app credentials) |
| `POST /sessions/v2/refresh/token` | Refresh access token | None |
| `GET /live/v1/homes` | Device status, battery SOC, temperatures | Bearer id_token |
| `GET /live/v2/homes/{id}/telemetry` | Live power flow data | Bearer id_token |

Authentication uses AWS Cognito under the hood. Tokens expire after 1 hour and are automatically refreshed using the stored refresh token, falling back to a full sign-in if needed.

---

## Known Limitations

- **Cloud-only** — no local API access. The PWRview unit (Raspberry Pi) blocks all inbound connections at the host firewall. All data routes through `generac-api.neur.io`.
- **30-second polling** — the Generac API updates per-second but HA polls every 30s to avoid excessive requests.
- **Single system** — currently uses the first home and first system returned by the API. Multi-home accounts are not tested.
- **Battery state values** — the `batteryState` field from the telemetry API currently returns `BATTERY_SOC_STATUS_UNSPECIFIED` in some conditions. The full enum is not yet documented.
- **No grid energy Wh from telemetry** — the telemetry endpoint returns instantaneous power only (`powerKw`). Lifetime energy for grid sensors is not yet available from a confirmed endpoint; those sensors will show unavailable until resolved.

---

## Troubleshooting

**Integration fails to set up / "invalid auth" error**
- Confirm your email and password work in the Generac PWRcell mobile app
- Check HA logs: Settings → System → Logs → filter `generac_pwrcell`

**Sensors show "unavailable"**
- Solar, grid, and consumption sensors come from the telemetry endpoint. If that returns `[]` (no new data), those sensors will be unavailable until the next non-empty poll. This is normal at night or during low-activity periods.
- Battery SOC and temperature always come from the homes endpoint and should always be available.

**Token expired / re-authentication needed**
- The integration refreshes tokens automatically. If refresh fails (e.g. after a password change), delete and re-add the integration.

---

## Contributing

Pull requests welcome. If you have a multi-battery setup, multiple PVL string configurations, or a generator attached, please open an issue with anonymised API response samples so additional device types can be supported.

---

## Disclaimer

This integration reverse-engineers the Generac PWRcell mobile app's API. It is not affiliated with or endorsed by Generac Power Systems. Use at your own risk. Generac may change their API at any time.

---

## License

MIT
