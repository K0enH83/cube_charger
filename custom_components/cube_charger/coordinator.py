
from __future__ import annotations
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant
from .api import CubeApi

_LOGGER = logging.getLogger(__name__)

class CubeCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: CubeApi, poll: int):
        super().__init__(hass, _LOGGER, name="Cube Charger", update_interval=timedelta(seconds=poll))
        self.api = api

    async def _async_update_data(self):
        boxes = await self.api.list_chargeboxes()
        return {b["chargeBoxId"]: b for b in boxes}
