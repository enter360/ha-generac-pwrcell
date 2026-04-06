"""Generac PWRcell Home Assistant integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .auth import GeneracAuth
from .const import CONF_API_BASE, CONF_USER_ID, DEFAULT_API_BASE, DOMAIN
from .coordinator import PWRcellCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Generac PWRcell from a config entry."""
    session = aiohttp_client.async_get_clientsession(hass)
    api_base = entry.data.get(CONF_API_BASE, DEFAULT_API_BASE) or DEFAULT_API_BASE

    auth = GeneracAuth(
        session=session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        api_base=api_base,
    )

    coordinator = PWRcellCoordinator(
        hass=hass,
        auth=auth,
        user_id=entry.data[CONF_USER_ID],
        api_base=api_base,
    )

    # First refresh — fails fast on bad credentials / unreachable API
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
