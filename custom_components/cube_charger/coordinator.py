from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CubeApi

DOMAIN = "cube_charger"

# Gebruik standaard Python logging
_LOGGER = logging.getLogger(__name__)


class CubeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Cube Charger."""

    def __init__(self, hass: HomeAssistant, api: CubeApi, poll_interval: int = 30) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,  # <-- geef hier de gewone logger door
            name=f"{DOMAIN}_coordinator",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data. Do not hardcode cars here.
        Expected shape for totals when implemented: {"RFID_XXX": 123.4, ...}
        """
        try:
            pong = await self.api.ping()

            # TODO: vervang None door jouw echte totals per idTag wanneer je API ready is
            totals_kwh: dict[str, float] | None = None
            # Voorbeeld (verwijderen zodra API is aangesloten):
            # totals_kwh = {"RFID_VW": 123.4, "RFID_PEU": 98.7}

            return {"pong": pong, "totals_kwh": totals_kwh}
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Cube Charger update failed: {err}") from err