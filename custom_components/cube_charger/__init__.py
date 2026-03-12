
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval
from .api import CubeApi
from .coordinator import CubeCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]
DOMAIN = "cube_charger"
STORE_VERSION = 1
STORE_KEY = "cube_history_state"

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    get = lambda key, default=None: entry.options.get(key, entry.data.get(key, default))

    api = CubeApi(get("base_url", "https://portal.cubecharging.com"), get("bearer_token"), get("verify_ssl", True))
    coord = CubeCoordinator(hass, api, int(get("poll_interval", 30)))
    await coord.async_config_entry_first_refresh()

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

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coord": coord,
        "connector_id": int(get("connector_id", 1)),
        "idtag_map": idtag_map,
        "energy_unit_active": get("energy_unit_active", "kWh"),
        "store": store,
        "store_data": store_data,
    }

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

    async def _aggregate_history(now):
        await _update_history_aggregates(hass, entry.entry_id)

    remove = async_track_time_interval(hass, _aggregate_history, timedelta(minutes=10))
    hass.data[DOMAIN][entry.entry_id]["remove_listener"] = remove

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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
