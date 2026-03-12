from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

DOMAIN = "cube_charger"


class CubeChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Cube Charger."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """First step: collect basic settings and create entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Basic validation – check required fields
            base_url = user_input.get("base_url")
            token = user_input.get("bearer_token")
            if not base_url or not token:
                errors["base_url"] = "cannot_connect" if not base_url else None
                errors["bearer_token"] = "invalid_auth" if not token else None

            # (optioneel) eenvoudige mapping-validatie
            mapping = user_input.get("idtag_mapping")
            if mapping is not None and not self._looks_like_mapping(mapping):
                errors["idtag_mapping"] = "unknown"

            if not errors:
                return self.async_create_entry(title="Cube Charger", data=user_input)

        schema = vol.Schema(
            {
                vol.Required("base_url", default="https://portal.cubecharging.com"): str,
                vol.Required("bearer_token"): str,
                vol.Optional("verify_ssl", default=True): bool,
                vol.Optional("poll_interval", default=30): int,
                vol.Optional(
                    "idtag_mapping",
                    default="RFID_VW:VW, RFID_PEU:Peugeot"
                ): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def _looks_like_mapping(raw: str) -> bool:
        """Very lenient format check: '<k>:<v>' pairs separated by commas."""
        if not raw:
            return True
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            return True
        for p in parts:
            if ":" not in p:
                return False
            k, v = p.split(":", 1)
            if not k.strip() or not v.strip():
                return False
        return True