
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


class CubeTransactionsCoordinator(DataUpdateCoordinator):
    """Fetch active transactions once per poll interval.

    Several entities (the enable switch, status sensor, who's-charging
    sensor, per-car sensors) all need the active-transactions list. Without
    this, each of them polled the Cube API independently on the same
    interval, multiplying request volume and making the API slow enough to
    trip both the "took longer than the scheduled update interval" and
    "setup ... is taking over 10 seconds" warnings.
    """

    def __init__(self, hass: HomeAssistant, api: CubeApi, poll: int, box_coordinator: CubeCoordinator):
        super().__init__(hass, _LOGGER, name="Cube Charger Transactions", update_interval=timedelta(seconds=poll))
        self.api = api
        self.box_coordinator = box_coordinator

    async def _async_update_data(self):
        cids = list((self.box_coordinator.data or {}).keys())
        chargebox_id = cids[0] if cids else None
        if not chargebox_id:
            return []
        return await self.api.active_transactions(chargebox_id)
