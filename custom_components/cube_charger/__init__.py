
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.components import webhook
from homeassistant.components.persistent_notification import async_create as async_create_notification
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval
from .api import CubeApi
from .coordinator import CubeCoordinator, CubeTransactionsCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT, Platform.SWITCH, Platform.NUMBER]
DOMAIN = "cube_charger"
STORE_VERSION = 1
STORE_KEY = "cube_history_state"

# OCPP 1.6 ChargePointStatus -> evcc-style A (ready) / B (connected) / C (charging).
_OCPP_STATUS_TO_EVCC = {
    "Charging": "C",
    "Preparing": "B",
    "SuspendedEVSE": "B",
    "SuspendedEV": "B",
    "Finishing": "B",
    "Available": "A",
    "Reserved": "A",
    "Unavailable": "A",
    "Faulted": "A",
}


def map_ocpp_status(status: str | None) -> str | None:
    """Map a raw OCPP 1.6 ChargePointStatus to evcc's A/B/C, defaulting unknown statuses to 'A'."""
    if status is None:
        return None
    return _OCPP_STATUS_TO_EVCC.get(status, "A")


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _verify_webhook_signature(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Verify the X-CubeSignature header: Base64(HMAC-SHA256(secret, raw_body))."""
    if not signature_header:
        return False
    mac = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode()
    return hmac.compare_digest(expected, signature_header)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


async def _handle_webhook(hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
    """Receive Cube Charging webhook events (see `webhook/subscription` on the portal API).

    Confirmed event shapes:
      - Session_started: chargeBoxId, connectorId, transactionId, idTag, meterStart (Wh), timestamp
      - Status_changed: chargeBoxId, connectorId, transactionId, status (OCPP ChargePointStatus), errorCode, timestamp
      - Session_progress: chargeBoxId, connectorId, transactionId, meterValue[].sampledValue[]
        (OCPP 1.6 MeterValues; the entry without a `measurand` is Energy.Active.Import.Register in Wh)
      - Session_stopped: chargeBoxId, connectorId, transactionId, idTag, meterStop (Wh), reason, timestamp
    `Status_progress` (flatter shape with `currentEnergy` in kWh) has also been seen in docs but wasn't in
    the advertised subscribable event list, so it's handled defensively rather than assumed reliable.

    Since this now trusts payload content for real state (status, session energy, total kWh), requests are
    verified against `webhook_secret` (X-CubeSignature: Base64 HMAC-SHA256) when one is configured. Without
    a configured secret, events are still processed (the URL itself is still an unguessable secret), but
    that means anyone who obtains the URL could inject fake status/energy - configuring the secret is
    strongly recommended once you've located it in the Cube portal.
    """
    raw_body = await request.read()
    data = hass.data.get(DOMAIN, {}).get(webhook_id)
    if not data:
        return web.Response(status=200)

    signature = request.headers.get("X-CubeSignature")
    secret = data.get("webhook_secret")
    if secret:
        if not _verify_webhook_signature(secret, raw_body, signature):
            _LOGGER.warning("cube_charger webhook: invalid or missing X-CubeSignature, rejecting request")
            return web.Response(status=401)
    elif signature:
        _LOGGER.debug("cube_charger webhook: X-CubeSignature present but no webhook_secret configured to verify it")

    try:
        payload = json.loads(raw_body) if raw_body else None
    except ValueError:
        payload = None

    event_type = request.headers.get("X-CubeEvent") or (payload.get("eventType") if isinstance(payload, dict) else None)
    _LOGGER.info("cube_charger webhook received (%s): %s", event_type, payload)
    hass.bus.async_fire(f"{DOMAIN}_webhook_event", {"eventType": event_type, "payload": payload})

    if isinstance(payload, dict):
        connector_id = data["connector_id"]
        if payload.get("connectorId") in (None, connector_id):
            state = data["webhook_state"]

            if event_type == "Session_started":
                meter_start = _to_float(payload.get("meterStart"))
                state.update(
                    transaction_id=payload.get("transactionId"),
                    idtag=payload.get("idTag"),
                    meter_start_wh=meter_start,
                    latest_meter_wh=meter_start,
                    status="Charging",
                )
            elif event_type == "Status_changed":
                state["status"] = payload.get("status")
                state["error_code"] = payload.get("errorCode")
            elif event_type == "Session_progress":
                for mv in payload.get("meterValue") or []:
                    for sv in mv.get("sampledValue") or []:
                        value = _to_float(sv.get("value"))
                        if value is None:
                            continue
                        measurand = sv.get("measurand")
                        if measurand is None:
                            state["latest_meter_wh"] = value
                        elif measurand == "Current.Offered":
                            state["latest_current_a"] = value
            elif event_type == "Status_progress":
                # Defensive/legacy-compat handling only - see docstring.
                current_energy_kwh = _to_float(payload.get("currentEnergy"))
                if current_energy_kwh is not None:
                    state["latest_meter_wh"] = current_energy_kwh * 1000.0
                state["idtag"] = payload.get("idTag") or state.get("idtag")
                state["transaction_id"] = payload.get("transactionId") or state.get("transaction_id")
            elif event_type == "Session_stopped":
                idtag = payload.get("idTag") or state.get("idtag")
                car = data["idtag_map"].get(idtag)
                meter_stop = _to_float(payload.get("meterStop"))
                meter_start = state.get("meter_start_wh")
                txn_id = payload.get("transactionId") or state.get("transaction_id")
                if car and meter_stop is not None and meter_start is not None and txn_id is not None:
                    kwh = max(meter_stop - meter_start, 0.0) / 1000.0
                    hass.async_create_task(
                        _accumulate_webhook_session(hass, webhook_id, car, str(txn_id), kwh, payload.get("timestamp"))
                    )
                if meter_stop is not None:
                    state["latest_meter_wh"] = meter_stop
                state.update(status="Available", transaction_id=None, idtag=None, meter_start_wh=None)

    hass.async_create_task(data["coord"].async_request_refresh())
    hass.async_create_task(data["tx_coord"].async_request_refresh())
    return web.Response(status=200)


async def _accumulate_webhook_session(hass: HomeAssistant, entry_id: str, car: str, txn_id: str, kwh: float, stop_timestamp) -> None:
    """Apply a Session_stopped's energy to the running total immediately, instead of waiting for the periodic history sync."""
    data = hass.data[DOMAIN][entry_id]
    store = data["store"]
    sdata = data["store_data"]
    processed = set(sdata.get("processed_pks", []))
    if txn_id in processed:
        return
    sdata["totals"][car] = sdata["totals"].get(car, 0.0) + kwh
    sdata["processed_pks"] = list(processed | {txn_id})
    if stop_timestamp:
        ts = str(stop_timestamp)
        if not sdata.get("last_stop_ts") or ts > sdata["last_stop_ts"]:
            sdata["last_stop_ts"] = ts
    await store.async_save(sdata)
    hass.bus.async_fire(f"{DOMAIN}_history_updated")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    get = lambda key, default=None: entry.options.get(key, entry.data.get(key, default))

    api = CubeApi(
        get("base_url", "https://portal.cubecharging.com"),
        get("bearer_token"),
        get("verify_ssl", True),
        int(get("request_timeout", 45)),
    )
    poll_interval = int(get("poll_interval", 30))
    coord = CubeCoordinator(hass, api, poll_interval)
    await coord.async_config_entry_first_refresh()

    tx_coord = CubeTransactionsCoordinator(hass, api, poll_interval, coord)
    await tx_coord.async_config_entry_first_refresh()

    mapping_str = get("idtag_mapping", "")
    idtag_map = {}
    for pair in [p.strip() for p in mapping_str.split(";") if p.strip()]:
        if "=" in pair:
            k, v = [x.strip() for x in pair.split("=", 1)]
            if k:
                idtag_map[k] = v or k

    store = Store(hass, STORE_VERSION, f"{DOMAIN}_{entry.entry_id}_{STORE_KEY}")
    store_data = await store.async_load() or {}
    store_data.setdefault("totals", {})
    store_data.setdefault("last_stop_ts", None)
    store_data.setdefault("processed_pks", [])

    boxes = list((coord.data or {}).values())
    box = boxes[0] if boxes else {}
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Cube Charging",
        name=box.get("description") or entry.title or "Cube Charger",
        model=box.get("chargePointModel"),
        sw_version=box.get("fwVersion"),
        serial_number=box.get("chargePointSerialNumber"),
        configuration_url=get("base_url", "https://portal.cubecharging.com"),
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coord": coord,
        "tx_coord": tx_coord,
        "connector_id": int(get("connector_id", 1)),
        "idtag_map": idtag_map,
        "energy_unit_active": get("energy_unit_active", "kWh"),
        "car_connected_entity": get("car_connected_entity", "") or None,
        "car_max_current_entity": get("car_max_current_entity", "") or None,
        "webhook_secret": get("webhook_secret", "") or None,
        "webhook_state": {
            "status": None,
            "error_code": None,
            "transaction_id": None,
            "idtag": None,
            "meter_start_wh": None,
            "latest_meter_wh": None,
            "latest_current_a": None,
        },
        "device_info": device_info,
        "store": store,
        "store_data": store_data,
    }

    webhook_id = entry.entry_id
    webhook.async_register(
        hass, DOMAIN, "Cube Charger", webhook_id, _handle_webhook, local_only=False
    )
    webhook_url = webhook.async_generate_url(hass, webhook_id)
    chargebox_id = box.get("chargeBoxId", "YOUR_CHARGEBOX_ID")
    async_create_notification(
        hass,
        (
            "Register this URL as a Cube Charging webhook subscription to get near-instant "
            "status updates instead of waiting for the next poll:\n\n"
            f"`{webhook_url}`\n\n"
            "Example (run yourself, replace YOUR_API_KEY):\n\n"
            "```\n"
            f'curl -X POST "{get("base_url", "https://portal.cubecharging.com")}/api/v1/CubeCharging/webhook/subscription" \\\n'
            '  -H "Authorization: Bearer YOUR_API_KEY" \\\n'
            '  -H "Content-Type: application/json" \\\n'
            "  -d '{\n"
            f'    "targetUrl": "{webhook_url}",\n'
            '    "events": ["Session_started", "Session_stopped", "Status_changed", "Session_progress"],\n'
            f'    "chargeBoxIds": ["{chargebox_id}"]\n'
            "  }'\n"
            "```\n\n"
            "Events are parsed for real-time status, session energy and instant "
            "total-energy updates. Every request includes an `X-CubeSignature` "
            "HMAC header - set `webhook_secret` in this integration's options "
            "once you've located it in the Cube portal, so requests can be "
            "cryptographically verified (without it, anyone with this URL could "
            "inject fake status/energy events)."
        ),
        title="Cube Charger: webhook available",
        notification_id=f"{DOMAIN}_webhook_{entry.entry_id}",
    )

    async def svc_start(call):
        chargebox_id = call.data.get("chargebox_id")
        connector_id = call.data.get("connector_id", hass.data[DOMAIN][entry.entry_id]["connector_id"])
        idtag = call.data.get("idtag")
        if not chargebox_id:
            data = hass.data[DOMAIN][entry.entry_id]
            cids = list((data["coord"].data or {}).keys())
            chargebox_id = cids[0] if cids else None
        sel = hass.states.get("select.cube_idtag")
        if not idtag and sel and sel.state:
            idtag = sel.state.split(" ")[0]
        await api.remote_start(chargebox_id, int(connector_id), idtag)

    async def svc_stop(call):
        chargebox_id = call.data.get("chargebox_id")
        if not chargebox_id:
            data = hass.data[DOMAIN][entry.entry_id]
            cids = list((data["coord"].data or {}).keys())
            chargebox_id = cids[0] if cids else None

        transaction_id = call.data.get("transaction_id")
        connector_id = call.data.get("connector_id")

        # Fallbacks: als niets is opgegeven, probeer actieve transactie op te halen
        if transaction_id is None and connector_id is None and chargebox_id:
            txs = await api.active_transactions(chargebox_id)
            if txs:
                # Neem de eerste; cast naar int indien mogelijk
                try:
                    transaction_id = int(txs[0].get("transactionPk"))
                except (TypeError, ValueError):
                    transaction_id = None
            # Als nog steeds niets, val terug op default connector uit opties/data
            if transaction_id is None and connector_id is None:
                connector_id = hass.data[DOMAIN][entry.entry_id]["connector_id"]

        if transaction_id is not None:
            await api.remote_stop(chargebox_id, transaction_id=int(transaction_id))
        elif connector_id is not None:
            await api.remote_stop(chargebox_id, connector_id=int(connector_id))
        else:
            raise ValueError("Stop: geef transaction_id of connector_id mee, of zorg dat er een actieve transactie is.")

    hass.services.async_register(DOMAIN, "start_session", svc_start)
    hass.services.async_register(DOMAIN, "stop_session", svc_stop)

    async def svc_sync_history(call):
        start_iso = call.data.get("startDate") or call.data.get("start_date")
        end_iso = call.data.get("endDate") or call.data.get("end_date")
        if start_iso or end_iso:
            await _update_history_aggregates_window(hass, entry.entry_id, start_iso, end_iso, append=True)
        else:
            await _update_history_aggregates(hass, entry.entry_id)
    hass.services.async_register(DOMAIN, "sync_history", svc_sync_history)

    async def svc_rebuild_history(call):
        start_iso = call.data.get("startDate") or call.data.get("start_date")
        end_iso = call.data.get("endDate") or call.data.get("end_date")
        if not (start_iso and end_iso):
            raise ValueError("rebuild_history requires startDate and endDate")
        data = hass.data[DOMAIN][entry.entry_id]
        sdata = data["store_data"]
        sdata["totals"] = {}
        sdata["processed_pks"] = []
        sdata["last_stop_ts"] = None
        await data["store"].async_save(sdata)
        await _update_history_aggregates_window(hass, entry.entry_id, start_iso, end_iso, append=True)
    hass.services.async_register(DOMAIN, "rebuild_history", svc_rebuild_history)

    async def svc_reset_chargebox(call):
        chargebox_id = call.data.get("chargebox_id")
        reset_type = call.data["reset_type"]  # Required
        if not chargebox_id:
            data = hass.data[DOMAIN][entry.entry_id]
            cids = list((data["coord"].data or {}).keys())
            chargebox_id = cids[0] if cids else None
        if not chargebox_id:
            raise ValueError("chargebox_id is required or must be auto-detectable")
        await api.reset_chargebox(chargebox_id, reset_type)

    hass.services.async_register(DOMAIN, "reset_chargebox", svc_reset_chargebox)

    async def _aggregate_history(now):
        await _update_history_aggregates(hass, entry.entry_id)

    remove = async_track_time_interval(hass, _aggregate_history, timedelta(minutes=10))
    hass.data[DOMAIN][entry.entry_id]["remove_listener"] = remove

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    webhook.async_unregister(hass, entry.entry_id)
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data and data.get("remove_listener"):
        data["remove_listener"]()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok

async def _update_history_aggregates(hass: HomeAssistant, entry_id: str):
    data = hass.data[DOMAIN][entry_id]
    sdata = data["store_data"]
    last_stop = sdata.get("last_stop_ts")
    start_iso = last_stop
    end_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    await _fetch_and_accumulate(hass, entry_id, start_iso, end_iso, update_last_stop=True, append=True)

async def _update_history_aggregates_window(hass: HomeAssistant, entry_id: str, start_iso: str | None, end_iso: str | None, append: bool = True):
    await _fetch_and_accumulate(hass, entry_id, start_iso, end_iso, update_last_stop=True, append=append)

async def _fetch_and_accumulate(hass: HomeAssistant, entry_id: str, start_iso: str | None, end_iso: str | None, update_last_stop: bool = True, append: bool = True):
    data = hass.data[DOMAIN][entry_id]
    api: CubeApi = data["api"]
    store = data["store"]
    sdata = data["store_data"]
    idmap = data["idtag_map"]
    coord = data["coord"]

    def _iso_or_none(x):
        if not x:
            return None
        try:
            if x.endswith('Z'):
                return x
            datetime.fromisoformat(x)
            return x
        except Exception:
            return None

    start_iso = _iso_or_none(start_iso)
    end_iso = _iso_or_none(end_iso) or datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    cids = list((coord.data or {}).keys())
    chargebox_id = cids[0] if cids else None

    LIMIT = 1000
    offset = 0
    processed = set(sdata.get("processed_pks", []))
    newly_processed = []
    added = 0.0
    new_last = sdata.get("last_stop_ts")

    while True:
        txns = await api.history_transactions(start_iso, end_iso, chargebox_id=chargebox_id, offset=offset, limit=LIMIT)
        if not txns:
            break
        for t in txns:
            txn_id = str(t.get("transactionPk"))
            if txn_id in processed:
                continue
            idtag = t.get("idTag")
            car = idmap.get(idtag)
            if not car:
                continue
            stop_val = t.get("stopValue")
            try:
                wh = float(stop_val)
                kwh = wh / 1000.0
            except (TypeError, ValueError):
                continue
            sdata["totals"][car] = sdata["totals"].get(car, 0.0) + kwh
            st = t.get("stopTimestamp")
            if st and (not new_last or st > new_last):
                new_last = st
            added += kwh
            newly_processed.append(txn_id)
        if len(txns) < LIMIT:
            break
        offset += LIMIT

    if newly_processed:
        sdata["processed_pks"] = list(set(processed).union(newly_processed))
    if update_last_stop and new_last:
        sdata["last_stop_ts"] = new_last

    if added > 0 or newly_processed:
        await store.async_save(sdata)
        hass.bus.async_fire(f"{DOMAIN}_history_updated")
