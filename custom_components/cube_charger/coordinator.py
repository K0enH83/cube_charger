from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CubeApi

DOMAIN = "cube_charger"


class CubeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Cube Charger."""

    def __init__(self, hass: HomeAssistant, api: CubeApi, poll_interval: int = 30) -> None:
        super().__init__(
            hass,
            logger=hass.helpers.logger.logging.getLogger(__name__),
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

            # TODO: Replace None with your real totals per idTag when API is implemented
            totals_kwh: dict[str, float] | None = None
            # Example (remove after API wired): totals_kwh = {"RFID_VW": 123.4, "RFID_PEU": 98.7}

            return {"pong": pong, "totals_kwh": totals_kwh}
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Cube Charger update failed: {err}") from err
