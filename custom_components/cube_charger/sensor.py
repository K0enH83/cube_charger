
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfElectricCurrent, UnitOfEnergy
from . import DOMAIN, map_ocpp_status
from .coordinator import CubeTransactionsCoordinator

class CubeCarTotalEnergySensor(SensorEntity, RestoreEntity):
    _attr_device_class = "energy"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = "total_increasing"

    def __init__(self, hass: HomeAssistant, entry_id: str, car_name: str):
        self.hass = hass
        self.entry_id = entry_id
        self.car_name = car_name
        self._attr_name = f"Cube {car_name} energie totaal"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_total_{car_name}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = float(last.state)
            except:  # noqa
                self._attr_native_value = 0.0
        self.hass.bus.async_listen(f"{DOMAIN}_history_updated", self._on_history_updated)

    @callback
    def _on_history_updated(self, _):
        data = self.hass.data[DOMAIN][self.entry_id]["store_data"]
        total = data["totals"].get(self.car_name, 0.0)
        self._attr_native_value = round(total, 3)
        self.async_write_ha_state()

class CubeCarActiveEnergySensor(CoordinatorEntity[CubeTransactionsCoordinator], SensorEntity):
    """Current-session energy (kWh) for one car, from the shared active-transactions poll."""

    _attr_device_class = "energy"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator: CubeTransactionsCoordinator, car_name: str, unit_active: str):
        super().__init__(coordinator)
        self.hass = hass
        self.entry_id = entry_id
        self.car_name = car_name
        self.unit_active = unit_active
        self._attr_name = f"Cube {car_name} actieve sessie"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_active_{car_name}"

    @property
    def native_value(self) -> float:
        idmap = self.hass.data[DOMAIN][self.entry_id]["idtag_map"]

        # Prefer the webhook-derived session energy (real OCPP MeterValues) for
        # this car's currently-tracked transaction; active_transactions has no
        # energy field at all, so without a webhook subscription this is 0.
        webhook_state = self.hass.data[DOMAIN][self.entry_id]["webhook_state"]
        if idmap.get(webhook_state.get("idtag")) == self.car_name and webhook_state.get("latest_meter_wh") is not None:
            start = webhook_state.get("meter_start_wh") or 0.0
            return round(max(webhook_state["latest_meter_wh"] - start, 0.0) / 1000.0, 3)

        value_kwh = 0.0
        for t in (self.coordinator.data or {}).get("transactions") or []:
            idtag = t.get("idTag")
            if idmap.get(idtag) != self.car_name:
                continue
            cur = t.get("currentEnergy")
            try:
                v = float(cur)
                if self.unit_active == "Wh":
                    v = v / 1000.0
                value_kwh += v
            except (TypeError, ValueError):
                continue
        return round(value_kwh, 3)

_CONNECTED_TRUE_STATES = {
    "on", "true", "1", "yes",
    "connected", "plugged_in", "plugged in",
    # Dutch: various car integrations (e.g. Volvo) report these as the raw state.
    "verbonden", "aangesloten", "ingeplugd", "gekoppeld",
}


def _find_connector_status(coordinator_data: dict | None, connector_id: int) -> dict | None:
    for c in (coordinator_data or {}).get("connector_status") or []:
        if c.get("connectorId") == connector_id:
            return c
    return None


def _parse_vendor_groups(vendor_id: str | None) -> list[float] | None:
    """Best-effort parse of the last 3 '-'-separated numeric groups in `vendorId`.

    Cube support has indicated (unconfirmed, per a support ticket) that the
    last 3 groups reflect per-phase current/energy, e.g. "...-054-056-056".
    No unit or scaling is assumed here - values are exposed as-is so real
    numbers from a live session can be compared against known current draw.
    """
    if not vendor_id:
        return None
    parts = vendor_id.split("-")
    if len(parts) < 3:
        return None
    values = []
    for p in parts[-3:]:
        try:
            values.append(float(p))
        except ValueError:
            return None
    return values


class CubeChargerStatusSensor(CoordinatorEntity[CubeTransactionsCoordinator], SensorEntity):
    """evcc-compatible status: 'C' while charging, 'B' while connected, else 'A'.

    'C' comes from a `Status_changed` webhook event or the polled OCPP status
    (`chargebox/status/{chargeBoxId}`), whichever is available - Cube is the
    only source of truth for "is it actually charging". For 'B', `car_connected_entity`
    (when configured) is trusted *in addition to* those, not only as a last
    resort: Cube's own status can report "Available" while a car is plugged
    in (its OCPP status classification doesn't necessarily match a plain
    plugged-in check), so `car_connected_entity` can upgrade an otherwise-'A'
    reading to 'B', but never downgrades a confirmed 'C'.
    """

    _attr_icon = "mdi:ev-station"

    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator: CubeTransactionsCoordinator, connector_id: int, car_connected_entity: str | None):
        super().__init__(coordinator)
        self.hass = hass
        self.entry_id = entry_id
        self.connector_id = connector_id
        self.car_connected_entity = car_connected_entity
        self._attr_name = "Cube Charger Status"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_evcc_status"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # native_value/extra_state_attributes always read car_connected_entity's
        # current state live, but without this, changes to it would only show up
        # whenever the coordinator next happens to refresh (up to poll_interval
        # away) instead of immediately. Track it directly so a plug/unplug is
        # reflected right away, and so the very first render after setup already
        # accounts for it (matters most when it's the only available status source).
        if self.car_connected_entity:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self.car_connected_entity], self._handle_car_connected_change
                )
            )

    @callback
    def _handle_car_connected_change(self, event) -> None:
        self.async_write_ha_state()

    def _is_car_connected(self) -> bool:
        if not self.car_connected_entity:
            return False
        state = self.hass.states.get(self.car_connected_entity)
        if not state:
            return False
        return state.state.lower() in _CONNECTED_TRUE_STATES

    @property
    def _webhook_status(self) -> str | None:
        return self.hass.data[DOMAIN][self.entry_id]["webhook_state"].get("status")

    @property
    def _polled_status_entry(self) -> dict | None:
        return _find_connector_status(self.coordinator.data, self.connector_id)

    @property
    def native_value(self) -> str:
        status = map_ocpp_status(self._webhook_status)
        if status is None:
            entry = self._polled_status_entry
            if entry and entry.get("status"):
                status = map_ocpp_status(entry["status"])
        if status is None:
            txs = (self.coordinator.data or {}).get("transactions") or []
            if any(t.get("connectorId") == self.connector_id for t in txs):
                status = "C"

        if status in (None, "A") and self._is_car_connected():
            return "B"
        return status or "A"

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {}
        entry = self._polled_status_entry
        if entry:
            attrs["ocpp_status"] = entry.get("status")
            attrs["ocpp_error_code"] = entry.get("errorCode")
            attrs["ocpp_status_timestamp"] = entry.get("statusTimestamp")
        # A webhook event is fresher than the last poll, so it wins when present.
        webhook_state = self.hass.data[DOMAIN][self.entry_id]["webhook_state"]
        if webhook_state.get("status") is not None:
            attrs["ocpp_status"] = webhook_state["status"]
        if webhook_state.get("error_code") is not None:
            attrs["ocpp_error_code"] = webhook_state["error_code"]
        return attrs


class CubeChargerOfferedCurrentSensor(CoordinatorEntity[CubeTransactionsCoordinator], SensorEntity):
    """Current (A) the EVSE is offering to the car, from a webhook `Session_progress` event.

    This is the OCPP `Current.Offered` measurand - the limit being offered,
    not a measurement of actual current draw - so it's informational only and
    not meant to feed evcc's currentL1/L2/L3 fields (those expect real
    measured current). Only populated if a webhook subscription is set up;
    otherwise stays unknown. Rides on the shared coordinator purely so it
    re-renders immediately when a webhook-triggered refresh happens, not
    because it needs the coordinator's own polled data.
    """

    _attr_device_class = "current"
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_icon = "mdi:current-ac"

    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator: CubeTransactionsCoordinator):
        super().__init__(coordinator)
        self.hass = hass
        self.entry_id = entry_id
        self._attr_name = "Cube Charger Offered Current"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_offered_current"

    @property
    def native_value(self) -> float | None:
        return self.hass.data[DOMAIN][self.entry_id]["webhook_state"].get("latest_current_a")


class CubeChargerVendorValueSensor(CoordinatorEntity[CubeTransactionsCoordinator], SensorEntity):
    """One of the 3 trailing numeric groups in the polled connector-status `vendorId`.

    Experimental/unconfirmed: per a Cube support ticket, these 3 groups are
    supposed to carry per-phase current or energy, but no unit or scaling has
    been confirmed. Exposed with no unit/device_class on purpose - compare
    the raw values against a known charging session (see `raw_vendor_id`
    attribute for the full string) to work out what they actually mean.
    """

    _attr_icon = "mdi:flash"

    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator: CubeTransactionsCoordinator, connector_id: int, index: int):
        super().__init__(coordinator)
        self.hass = hass
        self.entry_id = entry_id
        self.connector_id = connector_id
        self.index = index
        self._attr_name = f"Cube Charger Vendor Value {index + 1}"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_vendor_value_{index + 1}"

    @property
    def _entry(self) -> dict | None:
        return _find_connector_status(self.coordinator.data, self.connector_id)

    @property
    def native_value(self) -> float | None:
        entry = self._entry
        if not entry:
            return None
        values = _parse_vendor_groups(entry.get("vendorId"))
        return values[self.index] if values else None

    @property
    def extra_state_attributes(self) -> dict:
        entry = self._entry
        if entry and entry.get("vendorId"):
            return {"raw_vendor_id": entry["vendorId"]}
        return {}


class CubeChargerTotalEnergySensor(SensorEntity, RestoreEntity):
    """Cumulative synced energy (kWh) across all cars/idTags on this charger.

    Fed by the periodic (10 min) / manual history sync, not a live meter
    reading, since the Cube API does not expose live power values.
    """

    _attr_device_class = "energy"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = "total_increasing"

    def __init__(self, hass: HomeAssistant, entry_id: str):
        self.hass = hass
        self.entry_id = entry_id
        self._attr_name = "Cube Charger Energy Total"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_evcc_energy_total"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            try:
                self._attr_native_value = float(last.state)
            except:  # noqa
                self._attr_native_value = 0.0
        self.hass.bus.async_listen(f"{DOMAIN}_history_updated", self._on_history_updated)

    @callback
    def _on_history_updated(self, _):
        data = self.hass.data[DOMAIN][self.entry_id]["store_data"]
        total = sum(data["totals"].values())
        self._attr_native_value = round(total, 3)
        self.async_write_ha_state()


class CubeWhoIsChargingSensor(CoordinatorEntity[CubeTransactionsCoordinator], SensorEntity):
    """Text sensor showing which idTag/auto is currently charging."""
    _attr_icon = "mdi:account"

    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator: CubeTransactionsCoordinator):
        super().__init__(coordinator)
        self.hass = hass
        self.entry_id = entry_id
        self._attr_name = "Cube wie laadt nu"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_who_is_charging"

    def _active(self) -> list[dict]:
        idmap = self.hass.data[DOMAIN][self.entry_id]["idtag_map"]
        active = []
        for t in (self.coordinator.data or {}).get("transactions") or []:
            idtag = t.get("idTag")
            car = idmap.get(idtag)
            if car:
                active.append({
                    "car": car,
                    "idTag": idtag,
                    "transactionPk": t.get("transactionPk"),
                    "connectorId": t.get("connectorId"),
                    "currentEnergy_kWh": float(t.get("currentEnergy") or 0.0)
                })
        return active

    @property
    def native_value(self) -> str:
        active = self._active()
        return active[0]["car"] if active else "Geen"

    @property
    def extra_state_attributes(self) -> dict:
        active = self._active()
        return {"active": active} if active else {}

class CubeCarChargingBinarySensor(CoordinatorEntity[CubeTransactionsCoordinator], BinarySensorEntity):
    """Binary sensor per auto: on = deze auto laadt nu."""
    _attr_device_class = "power"

    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator: CubeTransactionsCoordinator, car_name: str):
        super().__init__(coordinator)
        self.hass = hass
        self.entry_id = entry_id
        self.car_name = car_name
        self._attr_name = f"Cube {car_name} laadt nu"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_charging_{car_name}"

    @property
    def is_on(self) -> bool:
        idmap = self.hass.data[DOMAIN][self.entry_id]["idtag_map"]
        tags = {k for k, v in idmap.items() if v == self.car_name}
        txs = (self.coordinator.data or {}).get("transactions") or []
        return any(t.get("idTag") in tags for t in txs)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    idmap = data["idtag_map"]
    tx_coord = data["tx_coord"]

    entities = []

    # evcc-compatible status + overall energy total
    entities.append(CubeChargerStatusSensor(hass, entry.entry_id, tx_coord, data["connector_id"], data["car_connected_entity"]))
    entities.append(CubeChargerOfferedCurrentSensor(hass, entry.entry_id, tx_coord))
    for i in range(3):
        entities.append(CubeChargerVendorValueSensor(hass, entry.entry_id, tx_coord, data["connector_id"], i))
    entities.append(CubeChargerTotalEnergySensor(hass, entry.entry_id))

    # cumulatief + actief per auto
    for car in sorted(set(idmap.values())):
        entities.append(CubeCarTotalEnergySensor(hass, entry.entry_id, car))
        entities.append(CubeCarActiveEnergySensor(hass, entry.entry_id, tx_coord, car, data["energy_unit_active"]))
        entities.append(CubeCarChargingBinarySensor(hass, entry.entry_id, tx_coord, car))

    # wie-laadt-nu sensor (1 tekstsensor)
    entities.append(CubeWhoIsChargingSensor(hass, entry.entry_id, tx_coord))

    for entity in entities:
        entity._attr_device_info = data["device_info"]

    async_add_entities(entities)
