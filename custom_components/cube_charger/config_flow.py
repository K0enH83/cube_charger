
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

DOMAIN = "cube_charger"

class CubeChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="Cube Charger", data=user_input)

        schema = vol.Schema({
            vol.Required("base_url", default="https://portal.cubecharging.com"): str,
            vol.Required("bearer_token"): str,
            vol.Optional("connector_id", default=1): int,
            vol.Optional("idtag_mapping", default=""): str,
            vol.Optional("energy_unit_active", default="kWh"): vol.In(["kWh", "Wh"]),
            vol.Optional("poll_interval", default=30): int,
            vol.Optional("verify_ssl", default=True): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CubeChargerOptionsFlowHandler(config_entry)

class CubeChargerOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # Use a private attribute to avoid assigning to a read-only property on base class
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)

        data = {**self._config_entry.data, **self._config_entry.options}
        schema = vol.Schema({
            vol.Optional("idtag_mapping", default=data.get("idtag_mapping", "")): str,
            vol.Optional("connector_id", default=data.get("connector_id", 1)): int,
            vol.Optional("poll_interval", default=data.get("poll_interval", 30)): int,
            vol.Optional("energy_unit_active", default=data.get("energy_unit_active", "kWh")): vol.In(["kWh", "Wh"]),
            vol.Optional("verify_ssl", default=data.get("verify_ssl", True)): bool,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
