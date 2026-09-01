"""Integrazione LIRCA per Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LircaApiClient, LircaAuthError, LircaConnectionError, LircaReading
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


class LircaDataUpdateCoordinator(DataUpdateCoordinator[list[LircaReading]]):
    """Coordinator che gestisce login + polling periodico."""

    def __init__(self, hass: HomeAssistant, client: LircaApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> list[LircaReading]:
        try:
            return await self.client.async_fetch_all()
        except LircaAuthError as err:
            raise UpdateFailed(f"Autenticazione fallita: {err}") from err
        except LircaConnectionError as err:
            raise UpdateFailed(f"Errore di connessione al portale LIRCA: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura l'integrazione a partire da una config entry."""
    session = async_get_clientsession(hass)
    client = LircaApiClient(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])

    coordinator = LircaDataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Rimuove l'integrazione."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
