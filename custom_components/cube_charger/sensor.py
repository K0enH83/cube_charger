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


def parse_mapping(raw: str | None) -> dict[str, str]:
    """Parse a mapping string 'RFID:Name, RFID2:Name2' to dict."""
    if not raw:
        return {}
    out: dict[str, str] = {}
    for pair in raw.split(","):
        if ":" in pair:
            k, v = pair.split(":", 1)
            k, v = k.strip(), v.strip()
            if k and v:
                out[k] = v
    return out


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: dict[str, Any] = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coord: CubeCoordinator | None = data.get("coord")
    api: CubeApi | None = data.get("api")
    if not coord or not api:
        return

    entities: list[SensorEntity] = [CubeStatusSensor(coord, entry)]

    # Mapping comes from config (no hardcoding in code)
    raw_map = entry.data.get("idtag_mapping") or entry.options.get("idtag_mapping")
    mapping = parse_mapping(raw_map)  # {'RFID_VW':'VW', ...}

    for idtag, label in mapping.items():
        entities.append(CubeCarEnergySensor(coord, entry, idtag=idtag, label=label))

    async_add_entities(entities)


class CubeStatusSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: CubeCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Cube Charger",
            manufacturer="Cube Charging",
            model="API",
        )

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    @property
    def native_value(self) -> Any:
        data = self._coordinator.data or {}
        pong = data.get("pong", {})
        return "who_is_charging" if pong.get("ok") else "unknown"

    async def async_update(self) -> None:
        await self._coordinator.async_request_refresh()


class CubeCarEnergySensor(SensorEntity):
    """Total loaded (kWh) per idTag (dynamic via mapping + coordinator)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:ev-plug-type2"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = "energy"
    _attr_state_class = "total"

    def __init__(self, coordinator: CubeCoordinator, entry: ConfigEntry, idtag: str, label: str) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._idtag = idtag
        self._label = label
        self._attr_name = f"{label} – Energy total"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_energy_total_{idtag}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Cube Charger",
            manufacturer="Cube Charging",
            model="API",
        )

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    @property
    def native_value(self) -> float | None:
        data = self._coordinator.data or {}
        totals = data.get("totals_kwh") or {}
        value = totals.get(self._idtag)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def async_update(self) -> None:
        await self._coordinator.async_request_refresh()
