"""Sensor platform for the Fronius Gen24 REST integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_LAST_UPDATE, DATA_SW_VERSION, DOMAIN
from .coordinator import FroniusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fronius Gen24 sensor entities."""
    coordinator: FroniusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FroniusSwVersionSensor(coordinator, entry),
            FroniusLastUpdateSensor(coordinator, entry),
        ]
    )


class FroniusSwVersionSensor(CoordinatorEntity[FroniusCoordinator], SensorEntity):
    """Diagnostic sensor reporting the GEN24 software version."""

    _attr_has_entity_name = True
    _attr_name = "GEN24 Software Version"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: FroniusCoordinator, entry: ConfigEntry) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_sw_version"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> str | None:
        """Return the current GEN24 firmware version string."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(DATA_SW_VERSION)


class FroniusLastUpdateSensor(CoordinatorEntity[FroniusCoordinator], SensorEntity):
    """Diagnostic sensor reporting the datetime of the last successful poll."""

    _attr_has_entity_name = True
    _attr_name = "Last Update"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: FroniusCoordinator, entry: ConfigEntry) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_update"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> datetime | None:
        """Return the UTC datetime of the last successful poll."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(DATA_LAST_UPDATE)
