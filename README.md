# Cube Charger – Home Assistant custom integration

A community integration for **Cube Charging** that adds your charger to Home Assistant.

> **Status:** Active development. The base is in place (config flow, status sensor, idTag select). Start/stop services and history features will be added iteratively.

---

## ✨ Features (current)

- **Config flow** (no YAML): enter `base_url`, `bearer_token`, `verify_ssl`, `poll_interval`.
- **Status sensor**: `sensor.cube_charger_status` shows `online` / `unknown` (backend connectivity).
- **idTag select**: `select.cube_charger_idtag` 
- **Automatic polling** via a `DataUpdateCoordinator`.
- Services: `start_session`, `stop_session`, `sync_history`, `rebuild_history`, `reset_chargebox`
- Options flow for idTags (manage via UI)
- kWh history aggregation per car (idTag)

**Roadmap (next iterations):**
-currentEnergy -> depending on fix Cube

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
3. Submit. The integration will connect and create entities right away.

---

## 🔎 Entities

| Entity                         | Type   | Description                                                  |
|-------------------------------|--------|--------------------------------------------------------------|
| `sensor.cube_charger_status`  | Sensor | `online` or `unknown` based on API connectivity              |
| `select.cube_charger_idtag`   | Select | Choose the active **idTag / car** (placeholder options now) |
| `sensor.cube_<mappedtag>_active_sessie`  | Sensor | Intended to show the current transaction energy consumption             |
| `sensor.cube_<mappedtag>_energie_totaal`  | Sensor | Sensor to accumulate total energy consumption on specified tag/car/person             |
| `sensor.cube_<mappedtag>_laadt_nu`  | Sensor | Sensor to indicate if tag is currently charging              |

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
- **Status stuck at `unknown`**  
