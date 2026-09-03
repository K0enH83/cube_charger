
from __future__ import annotations
import logging
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_CURRENT = 16
MIN_CURRENT = 10  # Cube's set-max-total-current enforces 10-32A.
MAX_CURRENT_CAP = 32


class CubeChargerMaxCurrentNumber(NumberEntity, RestoreEntity):
    """Max charging current requested by evcc.

    Forwarded to Cube's `chargebox/set-max-total-current` (confirmed working;
    Cube enforces a 10-32A range and rejects anything outside it) so the
    limit is genuinely applied at the charger, not just stored locally. If
    `car_max_current_entity` is also configured (a `number`/`input_number` on
    the car's own HA integration), the same value is forwarded there too, as
    an additional real-world cap. Both calls run in the background - like
    `switch.cube_charger_enable`, Cube's command can take a while to confirm,
    and evcc's `number.set_value` call shouldn't have to wait for that.
    """

    _attr_icon = "mdi:current-ac"
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_mode = NumberMode.BOX

    def __init__(self, hass: HomeAssistant, entry_id: str, max_current: int, car_max_current_entity: str | None):
        self.hass = hass
        self.entry_id = entry_id
        self.car_max_current_entity = car_max_current_entity
        self._attr_name = "Cube Charger Max Current"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_max_current"
        self._attr_native_min_value = MIN_CURRENT
        self._attr_native_max_value = max_current
        self._attr_native_value = max_current

        if car_max_current_entity and (state := hass.states.get(car_max_current_entity)):
            attrs = state.attributes
            self._attr_native_min_value = attrs.get("min", self._attr_native_min_value)
            self._attr_native_max_value = attrs.get("max", self._attr_native_max_value)
            self._attr_native_step = attrs.get("step", self._attr_native_step)
            try:
                self._attr_native_value = float(state.state)
            except (TypeError, ValueError):
                pass

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if not self.car_max_current_entity:
            # Only restore the last local value when there's no car entity to read the current value from.
            if (last := await self.async_get_last_state()) is not None:
                try:
                    self._attr_native_value = float(last.state)
                except (TypeError, ValueError):
                    pass

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        self.hass.async_create_task(self._async_apply(value))

    async def _async_apply(self, value: float) -> None:
        data = self.hass.data[DOMAIN][self.entry_id]
        api = data["api"]
        coord = data["coord"]
        cids = list((coord.data or {}).keys())
        chargebox_id = cids[0] if cids else None

        if chargebox_id and MIN_CURRENT <= value <= MAX_CURRENT_CAP:
            try:
                await api.set_max_current(chargebox_id, int(value))
            except Exception:
                _LOGGER.exception("cube_charger set_max_current failed")
        elif chargebox_id:
            _LOGGER.warning(
                "cube_charger set_max_current: %.0fA is outside Cube's %d-%dA range, not sent",
                value, MIN_CURRENT, MAX_CURRENT_CAP,
            )

        if not self.car_max_current_entity:
            return
        domain = self.car_max_current_entity.split(".", 1)[0]
        if domain not in ("number", "input_number"):
            _LOGGER.warning(
                "car_max_current_entity %s has an unsupported domain (expected number or input_number)",
                self.car_max_current_entity,
            )
            return
        try:
            await self.hass.services.async_call(
                domain,
                "set_value",
                {"entity_id": self.car_max_current_entity, "value": value},
                blocking=True,
            )
        except Exception:
            _LOGGER.exception("cube_charger: forwarding max current to %s failed", self.car_max_current_entity)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coord = data["coord"]
    cids = list((coord.data or {}).keys())
    max_current = DEFAULT_MAX_CURRENT
    if cids:
        box = coord.data[cids[0]]
        max_current = box.get("maximumConnectorCurrent") or box.get("maximumSystemCurrent") or DEFAULT_MAX_CURRENT
    max_current = max(MIN_CURRENT, min(int(max_current), MAX_CURRENT_CAP))
    entity = CubeChargerMaxCurrentNumber(hass, entry.entry_id, max_current, data["car_max_current_entity"])
    entity._attr_device_info = data["device_info"]
    async_add_entities([entity])
