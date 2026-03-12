
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from . import DOMAIN

class CubeIdTagSelect(SelectEntity):
    def __init__(self, options: list[str]):
        self._attr_name = "Cube: idTag"
        self._attr_unique_id = "cube_idtag"
        self._attr_options = options
        self._attr_current_option = options[0]

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    idmap = data["idtag_map"]
    options = [f"{k} ({v})" for k, v in idmap.items()] or ["RFID123456 (voorbeeld)"]
    async_add_entities([CubeIdTagSelect(options)])
