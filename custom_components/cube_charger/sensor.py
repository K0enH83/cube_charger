"""Sensor skeleton for Cube Charger."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CubeCoordinator
from .api import CubeApi

DOMAIN = "cube_charger"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cube Charger sensors from a config entry (skeleton)."""
    data: dict[str, Any] = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    # In een latere stap vullen we hass.data[DOMAIN][entry_id] in __init__.py.
    coordinator: CubeCoordinator | None = data.get("coord")
    api: CubeApi | None = data.get("api")

    # Als de integratie nog geen data heeft (we doen __init__ later), plaats een no-op.
    if not coordinator or not api:
        return

    sensors: list[SensorEntity] = [
        CubeStatusSensor(coordinator, entry),
    ]
    async_add_entities(sensors)


class CubeStatusSensor(SensorEntity):
    """Heel simpele status-sensor die de coordinator-data toont."""

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:ev-station"
    _attr_native_unit_of_measurement = None

    def __init__(self, coordinator: CubeCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_status"

        # DeviceInfo helpt om alles onder één apparaat te groeperen in HA UI
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Cube Charger",
            manufacturer="Cube Charging",
            model="API",
        )

    @property
    def available(self) -> bool:
        # Coordinator heeft data als laatste update gelukt is; zeer minimale check
