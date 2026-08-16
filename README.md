# Cube Charger – Home Assistant custom integration

A community integration for **Cube Charging** that adds your charger to Home Assistant.

> **Status:** Active development. The base is in place (config flow, status sensor, idTag select). Start/stop services and history features will be added iteratively.

---

## ✨ Features (current)

- **Config flow** (no YAML): enter `base_url`, `bearer_token`, `verify_ssl`, `poll_interval`.
- **evcc-compatible status sensor**: `sensor.cube_charger_status` reports `A` (ready) or `C` (charging).
- **Enable switch**: `switch.cube_charger_enable` starts/stops a charging session — usable as evcc's `enable`/`enabled` entity.
- **Max current number**: `number.cube_charger_max_current` satisfies evcc's required `setMaxCurrent` entity (see [evcc integration](#-evcc-integration) below for the important caveat).
- **idTag select**: `select.cube_charger_idtag`
- **Automatic polling** via a `DataUpdateCoordinator`.
- Services: `start_session`, `stop_session`, `sync_history`, `rebuild_history`, `reset_chargebox`
- Options flow for idTags (manage via UI)
- kWh history aggregation per car (idTag)

**Roadmap (next iterations):**
- currentEnergy -> depending on fix Cube
- Live power (W) reading, if/when the Cube API exposes meter values

---

## ✅ Requirements

- Home Assistant 2023.12+ (2024+ recommended)
- Working access to your **Cube Charging** portal (`base_url` + `bearer_token`)

---

## 🛠️ Installation

### HACS (recommended, as a Custom Repository)

1. Open **HACS → Integrations**  
2. Click **⋮ (menu) → Custom repositories**  
3. Add:
   - **Repository**: `https://github.com/K0enH83/cube_charger`
   - **Category**: **Integration**
4. Find **Cube Charger** in HACS and click **Download**  
5. **Restart Home Assistant**

### Manual (alternative)

1. Copy the folder `custom_components/cube_charger` from this repo to your HA config:  
   `config/custom_components/cube_charger`
2. **Restart Home Assistant**

---

## ⚙️ Configuration

1. Go to **Settings → Devices & Services → Add Integration** → search for **Cube Charger**
2. Fill in:
   - **Base URL** – e.g. `https://portal.cubecharging.com`
   - **Bearer token** - e.g. API key retrieved from Cube Portal
   - **connector_id** - 1 is the default
   - **idtag_mapping** - e.g the mapping of the RFIDS to cards or persons (for example RFID_1=Car1; RFID_2=Persony) -> this to map transactions to a car or person, especially helpfull when using multiple charge cards
   - **Poll interval** (seconds; default 30)
   - **Verify SSL**
   - **car_connected_entity** *(optional)* - entity ID of a car-side "plugged in" sensor (e.g. `binary_sensor.myauto_plugged_in`), used to report evcc status `B`
   - **car_max_current_entity** *(optional)* - entity ID of a car-side `number`/`input_number` that actually controls charging current (e.g. `number.myauto_charging_amps`); every value evcc sets is forwarded to it
3. Submit. The integration will connect and create entities right away.

---

## 🔎 Entities

| Entity                         | Type   | Description                                                  |
|-------------------------------|--------|--------------------------------------------------------------|
| `sensor.cube_charger_status`  | Sensor | evcc-compatible status: `A` (ready), `B` (connected, needs `car_connected_entity`) or `C` (charging) |
| `switch.cube_charger_enable`  | Switch | Starts/stops a charging session on the configured connector  |
| `number.cube_charger_max_current` | Number | Satisfies evcc's `setMaxCurrent`; forwarded to `car_max_current_entity` if configured, otherwise local-only |
| `sensor.cube_charger_energy_total` | Sensor | Cumulative synced kWh across all cars/idTags on this charger |
| `select.cube_charger_idtag`   | Select | Choose the active **idTag / car** (placeholder options now) |
| `sensor.cube_<mappedtag>_active_sessie`  | Sensor | Intended to show the current transaction energy consumption             |
| `sensor.cube_<mappedtag>_energie_totaal`  | Sensor | Sensor to accumulate total energy consumption on specified tag/car/person             |
| `sensor.cube_<mappedtag>_laadt_nu`  | Sensor | Sensor to indicate if tag is currently charging              |

---

## 🔌 evcc integration

This integration can be used as an evcc **"Home Assistant" charger**
(`type: homeassistant` in evcc's `chargers:` config), since evcc auto-discovers
Home Assistant instances and lets you pick suitable entities per role:

```yaml
chargers:
  - name: cube_charger
    type: homeassistant
    uri: http://homeassistant.local:8123
    status: sensor.cube_charger_status
    enabled: switch.cube_charger_enable
    enable: switch.cube_charger_enable
    maxcurrent: number.cube_charger_max_current
    energy: sensor.cube_charger_energy_total
```

### Bridging status `B` and `setMaxCurrent` through your car's own entities

The Cube Charging portal API itself has no live connector/plug state and no
endpoint to set the charging current (no OCPP `SetChargingProfile`
equivalent). If your car's own Home Assistant integration exposes a "plugged
in" sensor and a charging-current control, configure them in the integration
options and the full evcc feature set works:

- **`car_connected_entity`** – a `binary_sensor` (or any entity with an
  `on`/`off`/`true`/`false`/`connected`/`plugged_in` state) that reflects
  whether the car is plugged in. When set, `sensor.cube_charger_status`
  reports `B` whenever this entity is "on" but no session is active, and `C`
  once Cube reports an active transaction on the configured connector.
- **`car_max_current_entity`** – a `number` or `input_number` entity that
  actually limits the car's charging current. When set,
  `number.cube_charger_max_current` initializes its min/max/step/value from
  that entity and forwards every value evcc writes to it via
  `number.set_value` / `input_number.set_value`, so the limit is really
  applied. `switch.cube_charger_enable` still does the actual start/stop.

Without these two options, `sensor.cube_charger_status` can only report `A`
(ready) or `C` (charging) — it can't distinguish "connected, not yet
charging" — and `number.cube_charger_max_current` is a local, evcc-schema-only
value that isn't applied anywhere.

**Live power (W) reading:** energy is only available via the periodic
(10 min, or manually triggered) history sync, not a live meter value, so
`sensor.cube_charger_energy_total` updates in bursts rather than in real
time. If you need live power for evcc's PV-surplus control loop, consider
pairing this with a separate power meter (smart plug / CT clamp, or one
exposed by your car's integration) and pointing evcc's `power` at that
entity instead.

---

## 🧰 Services

The following services are available and can be called via **Developer Tools → Services** or automations:

- **`cube_charger.start_session`**  
  Starts a charging session on the charger.  
  **Fields:**  
  - `chargebox_id` (optional): ChargeBox ID (e.g., NL-1IC-XXXXXXX). Auto-detected if only one box.  
  - `connector_id` (optional): Connector ID (default: configured connector).  
  - `idtag` (optional): RFID tag for authorization (uses select entity if omitted).  

- **`cube_charger.stop_session`**  
  Stops the active charging session.  
  **Fields:**  
  - `chargebox_id` (optional): ChargeBox ID. Auto-detected if only one box.  
  - `transaction_id` (optional): OCPP transaction ID.  
  - `connector_id` (optional): Connector to stop (required if transaction_id not provided).  

- **`cube_charger.sync_history`**  
  Fetches historical finished sessions and accumulates energy per car/idTag.  
  **Fields:**  
  - `startDate` / `start_date` (optional): Start date in ISO-8601 format (e.g., 2023-10-01T00:00:00Z).  
  - `endDate` / `end_date` (optional): End date in ISO-8601 format (e.g., 2023-10-31T23:59:59Z).  

- **`cube_charger.rebuild_history`**  
  Resets totals and recomputes history within the specified date window.  
  **Fields:**  
  - `startDate` (required): Start date in ISO-8601 format (e.g., 2023-10-01T00:00:00Z).  
  - `endDate` (required): End date in ISO-8601 format (e.g., 2023-10-31T23:59:59Z).

- **`cube_charger.reset_chargebox`**  
  Resets the chargebox with either a Hard or Soft reset.  
  **Fields:**  
  - `chargebox_id` (optional): ChargeBox ID (auto-detected if only one box).  
  - `reset_type` (required): "Hard" for full reset or "Soft" for graceful reset.

---

## ❓ Troubleshooting

- **Integration not visible after install**  
  → Fully **restart Home Assistant** (Settings → System → **Restart**).
- **`sensor.cube_charger_status` stuck at `A`**  
  → Check `bearer_token` / `base_url` and that a car is actually plugged in and started via `switch.cube_charger_enable` or the `start_session` service; the sensor only flips to `C` while a transaction is active.

---

## 🙌 Contributors

- [@marconijmeijer](https://github.com/marconijmeijer) — evcc "Home Assistant charger" support: `switch.cube_charger_enable`, `number.cube_charger_max_current`, `sensor.cube_charger_status`/`energy_total`, and the `car_connected_entity`/`car_max_current_entity` bridge (v0.6.0).
