from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CubeCoordinator
from .api import CubeApi

DOMAIN = "cube_charger"


def parse_mapping(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    out: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            k, v = pair.split(":", 1)
            k, v = k.strip(), v.strip()
            if k and v:
                out[k] = v
    return out


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: dict[str, Any] = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coord: CubeCoordinator | None = data.get("coord")
    api: CubeApi | None = data.get("api")
    if not coord or not api:
        return

    raw_map = entry.data.get("idtag_mapping") or entry.options.get("idtag_mapping")
    mapping = parse_mapping(raw_map)
    names = list(mapping.values())

    async_add_entities([CubeIdTagSelect(hass, entry, coord, names)])


class CubeIdTagSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "idTag"
    _attr_icon = "mdi:card-account-details"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: CubeCoordinator, names: list[str]) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._names = names
        self._attr_options = names
        self._state_key = f"{DOMAIN}_{entry.entry_id}_selected_idtag_name"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_idtag_select"
        self._attr_current_option = self._get_saved_option() or (names[0] if names else None)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Cube Charger",
            manufacturer="Cube Charging",
            model="API",
        )

    def _get_saved_option(self) -> str | None:
        return self._hass.data.setdefault(DOMAIN, {}).setdefault(self._entry.entry_id, {}).get(
            "selected_idtag_name"
        )

    def _save_option(self, value: str | None) -> None:
        self._hass.data.setdefault(DOMAIN, {}).setdefault(self._entry.entry_id, {})[
            "selected_idtag_name"
        ] = value

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    @property
    def current_option(self) -> str | None:
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        if option not in self._names:
            return
        self._attr_current_option = option
        self._save_option(option)
        self.async_write_ha_state()
