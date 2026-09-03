
from __future__ import annotations
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN, connector_matches
from .coordinator import CubeTransactionsCoordinator

_LOGGER = logging.getLogger(__name__)


class CubeChargerEnableSwitch(CoordinatorEntity[CubeTransactionsCoordinator], SwitchEntity):
    """Start/stop charging on the configured connector.

    Exposed so it can be used as both the `enable` (control) and `enabled`
    (readback) entity of evcc's generic "Home Assistant" charger template.

    Reads active-transaction state from the shared CubeTransactionsCoordinator
    instead of polling the Cube API itself, and Cube's remote-start/-stop
    calls proxy an OCPP round trip to the physical charger that can take well
    beyond typical HTTP client timeouts (evcc's REST call to
    `/api/services/switch/turn_on` included). So the actual API call is fired
    in the background instead of being awaited here — HA (and evcc) get an
    immediate response with the optimistic new state, and it's corrected once
    the coordinator's next refresh confirms it (or immediately, on failure).
    """

    _attr_icon = "mdi:ev-station"

    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator: CubeTransactionsCoordinator, connector_id: int):
        super().__init__(coordinator)
        self.hass = hass
        self.entry_id = entry_id
        self.connector_id = connector_id
        self._attr_name = "Cube Charger Enable"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_enable"
        self._optimistic: bool | None = None

    @property
    def is_on(self) -> bool:
        if self._optimistic is not None:
            return self._optimistic
        txs = (self.coordinator.data or {}).get("transactions") or []
        return any(connector_matches(t.get("connectorId"), self.connector_id) for t in txs)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._optimistic = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs) -> None:
        self._optimistic = True
        self.async_write_ha_state()
        self.hass.async_create_task(self._async_call_service("start_session", desired_state=True))

    async def async_turn_off(self, **kwargs) -> None:
        self._optimistic = False
        self.async_write_ha_state()
        self.hass.async_create_task(self._async_call_service("stop_session", desired_state=False))

    async def _async_call_service(self, service: str, *, desired_state: bool) -> None:
        try:
            await self.hass.services.async_call(DOMAIN, service, {}, blocking=True)
        except Exception:
            _LOGGER.exception("cube_charger.%s failed", service)
            # Revert the optimistic state; the next coordinator refresh reconciles it anyway.
            self._optimistic = not desired_state
            self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    entity = CubeChargerEnableSwitch(hass, entry.entry_id, data["tx_coord"], data["connector_id"])
    entity._attr_device_info = data["device_info"]
    async_add_entities([entity])
