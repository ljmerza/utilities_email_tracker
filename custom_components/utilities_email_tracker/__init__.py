"""Utilities Email Tracker integration setup."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import UtilitiesEmailTrackerCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Utilities Email Tracker (config only)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Utilities Email Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = UtilitiesEmailTrackerCoordinator(
        hass,
        entry.entry_id,
        entry.data,
        entry.options,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Utilities Email Tracker config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    domain_data = hass.data.get(DOMAIN)
    if domain_data and entry.entry_id in domain_data:
        domain_data.pop(entry.entry_id)
        if not domain_data:
            hass.data.pop(DOMAIN)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
