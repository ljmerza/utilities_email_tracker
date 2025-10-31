"""Sensor platform for Utilities Email Tracker."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BILLS,
    ATTR_COUNT,
    ATTR_LAST_UPDATE,
    ATTR_SUMMARY,
    CONF_EMAIL,
    DOMAIN,
)
from .coordinator import UtilitiesEmailTrackerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Utilities Email Tracker sensors from a config entry."""
    coordinator: UtilitiesEmailTrackerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UtilitiesEmailTrackerSensor(coordinator, entry)])


class UtilitiesEmailTrackerSensor(CoordinatorEntity[UtilitiesEmailTrackerCoordinator], SensorEntity):
    """Representation of a utility bill summary sensor."""

    def __init__(self, coordinator: UtilitiesEmailTrackerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        email = entry.data.get(CONF_EMAIL, "account")

        self._attr_name = f"{email} Utility Bills"
        self._attr_unique_id = f"{entry.entry_id}_utility_bills"
        self._attr_icon = "mdi:file-document-outline"
        self._attr_translation_key = "utility_bills"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Utilities Email Tracker ({email})",
            "manufacturer": "Utilities Email Tracker",
            "model": "Email Bill Monitor",
        }

    @property
    def native_value(self) -> int:
        """Return the number of detected bills."""
        if not self.coordinator.data:
            return 0
        return int(self.coordinator.data.get(ATTR_COUNT, 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose detailed bill information."""
        if not self.coordinator.data:
            return {
                ATTR_BILLS: [],
                ATTR_SUMMARY: {},
                ATTR_COUNT: 0,
            }

        return {
            ATTR_BILLS: self.coordinator.data.get(ATTR_BILLS, []),
            ATTR_SUMMARY: self.coordinator.data.get(ATTR_SUMMARY, {}),
            ATTR_COUNT: self.coordinator.data.get(ATTR_COUNT, 0),
            ATTR_LAST_UPDATE: self.coordinator.data.get(ATTR_LAST_UPDATE),
        }

    @property
    def available(self) -> bool:
        """Return True if last update succeeded."""
        return self.coordinator.last_update_success
