
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import UnitOfEnergy
from . import DOMAIN
from .api import CubeApi

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

class CubeCarActiveEnergySensor(SensorEntity):
    _attr_device_class = "energy"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, hass: HomeAssistant, entry_id: str, api: CubeApi, car_name: str, unit_active: str):
        self.hass = hass
        self.entry_id = entry_id
        self.api = api
        self.car_name = car_name
        self.unit_active = unit_active
        self._attr_name = f"Cube {car_name} actieve sessie"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_active_{car_name}"

    async def async_update(self):
        data = self.hass.data[DOMAIN][self.entry_id]
        idmap = data["idtag_map"]
        coord = data["coord"]

        value_kwh = 0.0
        cids = list((coord.data or {}).keys())
        chargebox_id = cids[0] if cids else None
        if not chargebox_id:
            self._attr_native_value = None
            return

        txs = await self.api.active_transactions(chargebox_id)
        for t in txs:
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

        self._attr_native_value = round(value_kwh, 3)

class CubeWhoIsChargingSensor(SensorEntity):
    """Text sensor showing which idTag/auto is currently charging."""
    _attr_icon = "mdi:account"

    def __init__(self, hass: HomeAssistant, entry_id: str, api: CubeApi):
        self.hass = hass
        self.entry_id = entry_id
        self.api = api
        self._attr_name = "Cube wie laadt nu"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_who_is_charging"
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        data = self.hass.data[DOMAIN][self.entry_id]
        idmap = data["idtag_map"]
        coord = data["coord"]
        cids = list((coord.data or {}).keys())
        chargebox_id = cids[0] if cids else None
        if not chargebox_id:
            self._attr_native_value = "Geen"
            self._attr_extra_state_attributes = {}
            return
        txs = await self.api.active_transactions(chargebox_id)
        # Pak de eerste relevante transactie (of combineer meerdere)
        active = []
        for t in txs:
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
        if not active:
            self._attr_native_value = "Geen"
            self._attr_extra_state_attributes = {}
        else:
            # Indien meerdere, toon de eerste in state en allemaal in attributes
            self._attr_native_value = active[0]["car"]
            self._attr_extra_state_attributes = {
                "active": active
            }

class CubeCarChargingBinarySensor(BinarySensorEntity):
    """Binary sensor per auto: on = deze auto laadt nu."""
    _attr_device_class = "power"

    def __init__(self, hass: HomeAssistant, entry_id: str, api: CubeApi, car_name: str):
        self.hass = hass
        self.entry_id = entry_id
        self.api = api
        self.car_name = car_name
        self._attr_name = f"Cube {car_name} laadt nu"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_charging_{car_name}"
        self._attr_is_on = False

    async def async_update(self):
        data = self.hass.data[DOMAIN][self.entry_id]
        idmap = data["idtag_map"]
        # vind de idTags die bij deze auto horen
        tags = {k for k, v in idmap.items() if v == self.car_name}
        coord = data["coord"]
        cids = list((coord.data or {}).keys())
        chargebox_id = cids[0] if cids else None
        if not chargebox_id:
            self._attr_is_on = False
            return
        txs = await self.api.active_transactions(chargebox_id)
        self._attr_is_on = any(t.get("idTag") in tags for t in txs)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    api: CubeApi = data["api"]
    idmap = data["idtag_map"]

    entities = []

    # cumulatief + actief per auto
    for car in sorted(set(idmap.values())):
        entities.append(CubeCarTotalEnergySensor(hass, entry.entry_id, car))
        entities.append(CubeCarActiveEnergySensor(hass, entry.entry_id, api, car, data["energy_unit_active"]))
        entities.append(CubeCarChargingBinarySensor(hass, entry.entry_id, api, car))

    # wie-laadt-nu sensor (1 tekstsensor)
    entities.append(CubeWhoIsChargingSensor(hass, entry.entry_id, api))

    async_add_entities(entities, True)
