# Cube Charger – Home Assistant custom integration

A community integration for **Cube Charging** that adds your charger to Home Assistant.

> **Status:** Active development. The base is in place (config flow, status sensor, idTag select). Start/stop services and history features will be added iteratively.

---

## ✨ Features (current)

- **Config flow** (no YAML): enter `base_url`, `bearer_token`, `verify_ssl`, `poll_interval`.
- **Status sensor**: `sensor.cube_charger_status` shows `online` / `unknown` (backend connectivity).
- **idTag select**: `select.cube_charger_idtag` (placeholder options for now; will be managed via an options flow next).
- **Automatic polling** via a `DataUpdateCoordinator`.

**Roadmap (next iterations):**
- Services: `start_session`, `stop_session`, `sync_history`, `rebuild_history`
- Options flow for idTags (manage via UI)
- kWh history aggregation per car (idTag)

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
   - **Bearer token**
   - **connector_id** - 1 is the default
   - **idtag_mapping** - e.g the mapping of the charge cards used (for example RFID_1=Car1; RFID_2=Car2)
   - **Poll interval** (seconds; default 30)
   - **Verify SSL**
3. Submit. The integration will connect and create entities right away.

---

## 🔎 Entities

| Entity                         | Type   | Description                                                  |
|-------------------------------|--------|--------------------------------------------------------------|
| `sensor.cube_charger_status`  | Sensor | `online` or `unknown` based on API connectivity              |
| `select.cube_charger_idtag`   | Select | Choose the active **idTag / car** (placeholder options now) |

---

## 🧰 Services (coming soon)

The following services will be added and documented in upcoming releases:

- `cube_charger.start_session`  
- `cube_charger.stop_session`  
- `cube_charger.sync_history`  
- `cube_charger.rebuild_history`

They will appear under **Developer Tools → Services** and in `services.yaml` when available.

---

## ❓ Troubleshooting

- **Integration not visible after install**  
  → Fully **restart Home Assistant** (Settings → System → **Restart**).
- **Status stuck at `unknown`**  
