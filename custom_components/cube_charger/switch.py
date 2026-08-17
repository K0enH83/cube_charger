
from __future__ import annotations
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CubeChargerEnableSwitch(SwitchEntity):
    """Start/stop charging on the configured connector.

    Exposed so it can be used as both the `enable` (control) and `enabled`
    (readback) entity of evcc's generic "Home Assistant" charger template.

    Cube's remote-start/-stop calls proxy an OCPP round trip to the physical
    charger and can take well beyond typical HTTP client timeouts (evcc's
    REST call to `/api/services/switch/turn_on` included). So the actual API
    call is fired in the background instead of being awaited here — HA (and
    evcc) get an immediate response with the optimistic new state, and it's
    corrected on the next `async_update` (or immediately, if the call fails).
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
        self._attr_is_on = True
        self.async_write_ha_state()
        self.hass.async_create_task(self._async_call_service("start_session", desired_state=True))

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
        self.hass.async_create_task(self._async_call_service("stop_session", desired_state=False))

    async def _async_call_service(self, service: str, *, desired_state: bool) -> None:
        try:
            await self.hass.services.async_call(DOMAIN, service, {}, blocking=True)
        except Exception:
            _LOGGER.exception("cube_charger.%s failed", service)
            # Revert the optimistic state; the next async_update will reconcile it anyway.
            self._attr_is_on = not desired_state
            self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    entity = CubeChargerEnableSwitch(hass, entry.entry_id)
    entity._attr_device_info = data["device_info"]
    async_add_entities([entity])
