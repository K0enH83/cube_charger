
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
        for t in self.coordinator.data or []:
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

_CONNECTED_TRUE_STATES = {"on", "true", "1", "connected", "plugged_in", "yes"}

class CubeChargerStatusSensor(CoordinatorEntity[CubeTransactionsCoordinator], SensorEntity):
    """evcc-compatible status: 'C' while charging, 'B' while connected, else 'A'.

    Prefers the real OCPP status pushed via a `Status_changed` webhook event
    when one has been received. The Cube Charging polling API itself has no
    live connector/plug state, so without a webhook subscription, 'B'
    (connected, not charging) instead falls back to an external, car-side
    entity configured via `car_connected_entity` (e.g. the car's own "plugged
    in" binary sensor) - without that option either, it's 'A'/'C' only.
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
    def native_value(self) -> str:
        mapped = map_ocpp_status(self._webhook_status)
        if mapped is not None:
            return mapped
        txs = self.coordinator.data or []
        charging = any(t.get("connectorId") == self.connector_id for t in txs)
        if charging:
            return "C"
        if self._is_car_connected():
            return "B"
        return "A"

    @property
    def extra_state_attributes(self) -> dict:
        webhook_state = self.hass.data[DOMAIN][self.entry_id]["webhook_state"]
        attrs = {}
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
        for t in self.coordinator.data or []:
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
        return any(t.get("idTag") in tags for t in self.coordinator.data or [])

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    idmap = data["idtag_map"]
    tx_coord = data["tx_coord"]

    entities = []

    # evcc-compatible status + overall energy total
    entities.append(CubeChargerStatusSensor(hass, entry.entry_id, tx_coord, data["connector_id"], data["car_connected_entity"]))
    entities.append(CubeChargerOfferedCurrentSensor(hass, entry.entry_id, tx_coord))
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
