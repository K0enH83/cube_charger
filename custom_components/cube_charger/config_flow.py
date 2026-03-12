from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

DOMAIN = "cube_charger"


def _schema_user(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required("base_url", default=d.get("base_url", "https://portal.cubecharging.com")): str,
            vol.Required("bearer_token", default=d.get("bearer_token", "")): str,
            vol.Optional("verify_ssl", default=d.get("verify_ssl", True)): bool,
            vol.Optional("poll_interval", default=d.get("poll_interval", 30)): int,
            vol.Optional("idtag_mapping", default=d.get("idtag_mapping", "")): str,
        }
    )


class CubeChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Cube Charger."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Cube Charger", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema_user())
