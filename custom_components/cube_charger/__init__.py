"""Cube Charger integration: entry setup skeleton.

Zet de API + DataUpdateCoordinator klaar en laad de platformen (sensor).
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import CubeApi
from .coordinator import CubeCoordinator

DOMAIN = "cube_charger"
PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cube Charger from a config entry."""
    base_url = entry.data.get("base_url", "https://portal.cubecharging.com")
    bearer_token = entry.data.get("bearer_token", "")
    verify_ssl = bool(entry.data.get("verify_ssl", True))
    poll_interval = int(entry.data.get("poll_interval", 30))

    api = CubeApi(base_url, bearer_token, verify_ssl)
    coordinator = CubeCoordinator(hass, api, poll_interval=poll_interval)

    # Eerste refresh (asynchroon) zodat coordinator.data beschikbaar is voor entiteiten
    await coordinator.async_config_entry_first_refresh()

    # Bewaar referenties in hass.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coord": coordinator,
    }

    # Laad platformen (nu: sensor)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle unload of a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
