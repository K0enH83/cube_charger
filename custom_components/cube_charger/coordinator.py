"""DataUpdateCoordinator skeleton for Cube Charger."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

# Je kunt dit domein ook uit manifest.json lezen; voor nu hardcoderen we het hier
DOMAIN = "cube_charger"


class CubeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coördineert periodieke data-updates voor de Cube Charger integratie."""

    def __init__(self, hass: HomeAssistant, api: Any, poll_interval: int = 30) -> None:
        """Maak de coordinator aan.

        api: een instance van CubeApi (zie api.py)
        poll_interval: seconds tussen polls
        """
        super().__init__(
            hass,
            logger=hass.helpers.logger.logging.getLogger(__name__),
            name=f"{DOMAIN}_coordinator",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Haal data op van de backend. Gooi UpdateFailed bij fouten."""
        try:
            # Voor nu: minimale “ping”; later vervangen door echte calls
            pong = await self.api.ping()
            # Return een dictionary waarop entiteiten zich kunnen abonneren
            return {"pong": pong}
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Cube Charger update failed: {err}") from err
