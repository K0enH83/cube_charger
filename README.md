# Cube Charger – Home Assistant custom integration - EVCC COMPATIBLE

A community integration for **Cube Charging** that adds your charger to Home Assistant AND that can be used with evcc

> **Status:** Active development. The base is in place (config flow, status sensor, idTag select). Start/stop services and history features will be added iteratively.

---

## ✨ Features (current)

- **Config flow** (no YAML): enter `base_url`, `bearer_token`, `verify_ssl`, `poll_interval`.
- **evcc-compatible status sensor**: `sensor.cube_charger_status` reports `A` (ready), `B` (connected) or `C` (charging) — sourced from the real, always-polled OCPP status (`chargebox/status/{chargeBoxId}`), overridden by an even fresher webhook event when one has just arrived.
- **Enable switch**: `switch.cube_charger_enable` starts/stops a charging session — usable as evcc's `enable`/`enabled` entity.
- **Max current number**: `number.cube_charger_max_current` satisfies evcc's required `setMaxCurrent` entity (see [evcc integration](#-evcc-integration) below for the important caveat).
- **idTag select**: `select.cube_charger_idtag`
- **Automatic polling** via two shared `DataUpdateCoordinator`s (chargebox details, active transactions) — every entity that needs live transaction state reads from the same poll instead of each making its own API call.
- **Webhook receiver** (see [Webhook support](#-webhook-support) below) — parses Cube's `Session_started`/`Session_stopped`/`Status_changed`/`Session_progress` events for real-time status, session energy and instant total-energy updates, and triggers an immediate refresh either way.
- Services: `start_session`, `stop_session`, `sync_history`, `rebuild_history`, `reset_chargebox`
- Options flow for idTags (manage via UI)
- kWh history aggregation per car (idTag)

**Roadmap (next iterations):**
- Live power (W): now that real current (`Current.Import`) is confirmed, an estimated-power sensor (current × an assumed voltage) is feasible - not added yet since it'd be an approximation, not a real measurement
- Confirm whether `Current.Import` is ever reported per-phase (with a `phase` field) so it could feed evcc's `currentL1/L2/L3` directly - only a single, phase-less reading has been confirmed so far
- Confirm the meaning/unit/scaling of `chargebox/status`'s `vendorId`-encoded values (see below) from a real charging session, then give them a proper name/unit/device_class
- Confirm whether `Status_progress` is a real, current webhook event or stale docs

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
   - **car_connected_entity** *(optional, recommended)* - entity ID of a car-side "plugged in" sensor (e.g. `binary_sensor.myauto_plugged_in`); upgrades evcc status `A` to `B` when Cube's own status doesn't reflect it being plugged in
   - **car_max_current_entity** *(optional)* - entity ID of a car-side `number`/`input_number` that actually controls charging current (e.g. `number.myauto_charging_amps`); every value evcc sets is forwarded to it
   - **webhook_secret** *(optional, not recommended currently — see [Webhook support](#-webhook-support))* - verifies the `X-CubeSignature` header on incoming webhook events, but only if you've independently confirmed Cube actually signs your subscription's events with it
3. Submit. The integration will connect and create entities right away, grouped under a single **Cube Charger** device that you can assign to an area/room (Settings → Devices & Services → Cube Charger → the device page has an **Area** picker).

---

## 🔎 Entities

| Entity                         | Type   | Description                                                  |
|-------------------------------|--------|--------------------------------------------------------------|
| `sensor.cube_charger_status`  | Sensor | evcc-compatible status: `A` (ready), `B` (connected) or `C` (charging) — real OCPP status, see above |
| `switch.cube_charger_enable`  | Switch | Starts/stops a charging session on the configured connector  |
| `number.cube_charger_max_current` | Number | Satisfies evcc's `setMaxCurrent`; forwarded to `car_max_current_entity` if configured, otherwise local-only |
| `sensor.cube_charger_energy_total` | Sensor | Cumulative synced kWh across all cars/idTags on this charger |
| `sensor.cube_charger_current` | Sensor | OCPP `Current.Import` (A) — real measured charging current, from a webhook `Session_progress` event |
| `sensor.cube_charger_offered_current` | Sensor | OCPP `Current.Offered` (A) from a webhook `Session_progress` event — informational, the offered limit, not measured draw |
| `sensor.cube_charger_vendor_value_1/2/3` | Sensor | **Experimental**, unconfirmed — the 3 trailing numeric groups from the polled `vendorId` field; see [Live status polling](#-live-status-polling-chargeboxstatus) |
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

`sensor.cube_charger_status` normally already gets a real `A`/`B`/`C` from
[live status polling](#-live-status-polling-chargeboxstatus) - no extra
setup needed for that on its own. In practice, Cube's own OCPP status can
still report `Available` (`A`) while the car is physically plugged in (its
status classification doesn't necessarily match a plain plugged-in check),
so it's worth setting `car_connected_entity` anyway to catch that:

- **`car_connected_entity`** – any entity reflecting whether the car is
  plugged in. Its state is matched case-insensitively against a fixed list:
  `on`, `true`, `1`, `yes`, `connected`, `plugged_in`/`plugged in`, and the
  Dutch `verbonden`, `aangesloten`, `ingeplugd`, `gekoppeld` (some car
  integrations, e.g. Volvo's, report a translated word directly as the raw
  state). When it matches, the status is upgraded to `B` - it can turn an
  `A` into a `B`, but never overrides an already-confirmed `C`. If your car
  integration reports something not in that list, check the exact value via
  **Developer Tools → States** and open an issue/PR to add it.
- **`car_max_current_entity`** – a `number` or `input_number` entity that
  actually limits the car's charging current - the Cube API itself has no
  way to *set* the charging current (no OCPP `SetChargingProfile`
  equivalent). When set, `number.cube_charger_max_current` initializes its
  min/max/step/value from that entity and forwards every value evcc writes
  to it via `number.set_value` / `input_number.set_value`, so the limit is
  really applied. `switch.cube_charger_enable` still does the actual
  start/stop.

Without `car_max_current_entity`, `number.cube_charger_max_current` is a
local, evcc-schema-only value that isn't applied anywhere.

**Why `switch.cube_charger_enable` responds instantly:** Cube's remote-start/
-stop calls proxy an OCPP round trip to the physical charger and can take
much longer than typical HTTP client timeouts — including evcc's own request
to Home Assistant's `POST /api/services/switch/turn_on`. So the switch
applies the requested state optimistically and fires the actual Cube API
call in the background; if that call fails, the state is reverted (and the
next poll reconciles it either way). If evcc still reports a charger-enable
error, check the Home Assistant log for `cube_charger.start_session failed`
/ `cube_charger.stop_session failed` for the real cause.

**Why entities share one `active_transactions` poll:** the switch, status
sensor, "who's charging" sensor and per-car sensors all need the same
active-transaction data. Each polling independently (as in versions before
0.8.0) multiplied API calls ~5x per interval and could trip Home Assistant's
"took longer than the scheduled update interval" / "setup ... is taking over
10 seconds" warnings. They now all read from one shared
`CubeTransactionsCoordinator` poll instead.

**Live power (W) reading:** energy is only available via the periodic
(10 min, or manually triggered) history sync, not a live meter value, so
`sensor.cube_charger_energy_total` updates in bursts rather than in real
time. If you need live power for evcc's PV-surplus control loop, consider
pairing this with a separate power meter (smart plug / CT clamp, or one
exposed by your car's integration) and pointing evcc's `power` at that
entity instead.

---

## 🪝 Webhook support

The Cube Charging portal API supports webhook subscriptions
(`POST`/`PUT /api/v1/CubeCharging/webhook/subscription`) that push events —
`Session_started`, `Session_stopped`, `Status_changed`, `Session_progress` —
to a URL of your choice, instead of you having to poll for them. This
integration registers a Home Assistant webhook receiver and parses all four:

- **`Status_changed`** — the real OCPP `status` (e.g. `Charging`,
  `Preparing`, `SuspendedEVSE`) is mapped straight to evcc's `A`/`B`/`C`.
  Since [live status polling](#-live-status-polling-chargeboxstatus) already
  sources the same real status without needing a webhook, this mainly makes
  status changes near-instant instead of waiting for the next poll. The raw
  OCPP status and `errorCode` are also exposed as attributes.
- **`Session_progress`** — parses the OCPP `meterValue`/`sampledValue`
  payload: the default-measurand entry (`Energy.Active.Import.Register`, Wh)
  feeds the per-car active-session sensor (`sensor.cube_<car>_actieve_sessie`)
  with a real value for the first time — `active_transactions` has no energy
  field at all, so without a webhook subscription this sensor is always 0.
  `Current.Import` (real measured current, A) is exposed as
  `sensor.cube_charger_current`; `Current.Offered` (the offered limit, not
  measured draw) as `sensor.cube_charger_offered_current` — informational
  only, don't wire it into evcc's `currentL1/L2/L3`.
- **`Session_started`** / **`Session_stopped`** — track `meterStart`/
  `meterStop` (Wh) to compute the session's energy, and `Session_stopped`
  applies that delta to the car's running total **immediately**
  (`sensor.cube_<car>_energie_totaal` / `sensor.cube_charger_energy_total`)
  instead of waiting for the periodic (10 min) history sync. The same
  transaction ID is marked processed so the later sync doesn't double-count it.

Every event also triggers an immediate refresh of both polling coordinators,
so even entities not directly fed by a webhook update close to instantly
instead of waiting up to `poll_interval` seconds.

**Setup:** after (re)start, look for a persistent notification titled
**"Cube Charger: webhook available"** — it has your instance's webhook URL
and a ready-to-fill-in `curl` command to register the subscription (fill in
your own `Authorization: Bearer` API key; it's never entered into Home
Assistant for this). If you have Home Assistant Cloud (Nabu Casa), that URL
is already publicly reachable with no extra setup. Without a subscription,
everything falls back to the polling-only behavior described above.

**Security — `webhook_secret` (currently unreliable, opt-in only):** every
webhook request carries an `X-CubeSignature` header (Base64 HMAC-SHA256 of
the raw body), which `webhook_secret` can verify. Earlier versions
auto-generated one and enforced it by default; that's been reverted after
real-world testing showed Cube's `webhook/subscription` API accepts a
`secret` in the `POST`/`PUT` body (200 OK, `updatedAt` changes) but doesn't
actually sign subsequent event deliveries with it — real events kept
arriving unsigned and were silently rejected the moment enforcement was on,
breaking real-time updates entirely. So for now: **leave `webhook_secret`
empty** (the default). Only set it if you've independently confirmed, for
your own subscription, that Cube signs events with that exact value — and
if you ever see `invalid or missing X-CubeSignature` in the log after
setting it, clear the option immediately, since it blocks *all* real events
while it's misconfigured, not just forged ones. Without a secret set,
events are still processed (the webhook URL itself is still an unguessable
secret) with no verification.

Not-yet-confirmed: a flatter `Status_progress` event (with `currentEnergy` in
kWh) has turned up in some docs but wasn't in the advertised subscribable
event list — it's handled defensively if it ever arrives, but isn't assumed
reliable.

---

## 🔬 Live status polling (`chargebox/status`)

Alongside the existing `chargebox/details` and `active_transactions` polls,
this integration also polls `GET /api/v1/CubeCharging/chargebox/status/{chargeBoxId}`
every `poll_interval`, which — unlike anything else in the Cube API —
returns the connector's real OCPP `status` (e.g. `Charging`, `Preparing`)
directly, without needing a webhook subscription or `car_connected_entity`
at all. This is what `sensor.cube_charger_status` uses by default now; a
webhook `Status_changed` event, when one arrives, just makes the change
show up sooner.

The same response also has a `vendorId` field — a long, otherwise-opaque
identifier string — whose trailing 3 `-`-separated numeric groups Cube
support has said (via a support ticket, unconfirmed) carry per-phase
current or energy, e.g. `...-054-056-056`. Since neither the unit nor the
scaling is confirmed, these are exposed as-is:
`sensor.cube_charger_vendor_value_1/2/3` (no unit/device_class), with the
full raw string as a `raw_vendor_id` attribute. **If you can compare these
values against known current/energy during a real charging session, please
report back (or open an issue/PR)** so they can get a proper unit and be
wired into evcc's `currentL1/L2/L3` or `power` if they turn out to be real
measured values rather than something offered/nominal.

This poll is best-effort: if it fails, it's logged at debug level and the
rest of the shared poll (transactions, switch, energy) is unaffected —
`sensor.cube_charger_status` then falls back to the active-transaction +
`car_connected_entity` heuristic described above.

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

- [@marconijmeijer](https://github.com/marconijmeijer) — evcc "Home Assistant charger" support: `switch.cube_charger_enable`, `number.cube_charger_max_current`, `sensor.cube_charger_status`/`energy_total`, the `car_connected_entity`/`car_max_current_entity` bridge, and grouping all entities under a single assignable device (v0.6.0–v0.7.0).
