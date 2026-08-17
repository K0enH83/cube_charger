
from __future__ import annotations
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from . import DOMAIN


class CubeChargerEnableSwitch(SwitchEntity):
    """Start/stop charging on the configured connector.

    Exposed so it can be used as both the `enable` (control) and `enabled`
    (readback) entity of evcc's generic "Home Assistant" charger template.
    """

    _attr_icon = "mdi:ev-station"

    def __init__(self, hass: HomeAssistant, entry_id: str):
        self.hass = hass
        self.entry_id = entry_id
        self._attr_name = "Cube Charger Enable"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_enable"
        self._attr_is_on = False

    async def async_update(self) -> None:
        data = self.hass.data[DOMAIN][self.entry_id]
        api = data["api"]
        coord = data["coord"]
        connector_id = data["connector_id"]
        cids = list((coord.data or {}).keys())
        chargebox_id = cids[0] if cids else None
        if not chargebox_id:
            self._attr_is_on = False
            return
        txs = await api.active_transactions(chargebox_id)
        self._attr_is_on = any(t.get("connectorId") == connector_id for t in txs)

    async def async_turn_on(self, **kwargs) -> None:
        await self.hass.services.async_call(DOMAIN, "start_session", {}, blocking=True)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.services.async_call(DOMAIN, "stop_session", {}, blocking=True)
        self._attr_is_on = False
        self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    entity = CubeChargerEnableSwitch(hass, entry.entry_id)
    entity._attr_device_info = data["device_info"]
    async_add_entities([entity])
