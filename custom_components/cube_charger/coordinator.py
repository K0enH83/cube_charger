
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
    """Fetch active transactions and per-connector status once per poll interval.

    Several entities (the enable switch, status sensor, who's-charging
    sensor, per-car sensors) all need the active-transactions list. Without
    this, each of them polled the Cube API independently on the same
    interval, multiplying request volume and making the API slow enough to
    trip both the "took longer than the scheduled update interval" and
    "setup ... is taking over 10 seconds" warnings. connector_status rides
    along on the same poll for the same reason - it's the only source of a
    real, always-available (not webhook-dependent) OCPP status.

    `.data` is `{"transactions": [...], "connector_status": [...]}`.
    """

    def __init__(self, hass: HomeAssistant, api: CubeApi, poll: int, box_coordinator: CubeCoordinator):
        super().__init__(hass, _LOGGER, name="Cube Charger Transactions", update_interval=timedelta(seconds=poll))
        self.api = api
        self.box_coordinator = box_coordinator

    async def _async_update_data(self):
        cids = list((self.box_coordinator.data or {}).keys())
        chargebox_id = cids[0] if cids else None
        if not chargebox_id:
            return {"transactions": [], "connector_status": []}
        transactions = await self.api.active_transactions(chargebox_id)
        try:
            connector_status = await self.api.connector_status(chargebox_id)
        except Exception:
            # Newer, less-proven endpoint - don't let a hiccup here take down
            # the transactions poll (and everything derived from it) too.
            _LOGGER.debug("cube_charger: connector_status poll failed", exc_info=True)
            connector_status = []
        return {"transactions": transactions, "connector_status": connector_status}
