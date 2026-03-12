from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

DOMAIN = "cube_charger"


class CubeChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow voor Cube Charger."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Eerste stap: vraag basis-instellingen op en maak een entry aan."""
        if user_input is not None:
            # In __init__.py lezen we deze waarden uit entry.data
            return self.async_create_entry(title="Cube Charger", data=user_input)

        schema = vol.Schema(
            {
                vol.Required("base_url", default="https://portal.cubecharging.com"): str,
                vol.Required("bearer_token"): str,
                vol.Optional("verify_ssl", default=True): bool,
                vol.Optional("poll_interval", default=30): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
