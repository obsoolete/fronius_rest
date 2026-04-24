"""Number platform for the Fronius Gen24 REST integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LAST_EXPORT_LIMIT, DATA_EXPORT_ENABLED, DATA_EXPORT_POWER_LIMIT, DOMAIN
from .coordinator import FroniusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fronius Gen24 number entities."""
    coordinator: FroniusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FroniusExportPowerLimitNumber(coordinator, entry)])


class FroniusExportPowerLimitNumber(CoordinatorEntity[FroniusCoordinator], NumberEntity):
    """Number entity for setting the export soft-limit power value."""

    _attr_has_entity_name = True
    _attr_name = "Export Power Limit"
    _attr_native_min_value = 0
    _attr_native_max_value = 20000
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, coordinator: FroniusCoordinator, entry: ConfigEntry) -> None:
        """Initialise the number entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_export_power_limit"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        """Return the live limit when export is on, or the remembered limit when off."""
        if self.coordinator.data is None:
            return self.coordinator.config_entry.data.get(CONF_LAST_EXPORT_LIMIT)
        if self.coordinator.data.get(DATA_EXPORT_ENABLED):
            return self.coordinator.data.get(DATA_EXPORT_POWER_LIMIT)
        return self.coordinator.config_entry.data.get(CONF_LAST_EXPORT_LIMIT)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new limit; send to the inverter only when export is enabled."""
        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            data={**self.coordinator.config_entry.data, CONF_LAST_EXPORT_LIMIT: value},
        )
        if self.coordinator.data and self.coordinator.data.get(DATA_EXPORT_ENABLED):
            await self.coordinator.async_set_export_power_limit(value)
        else:
            self.async_write_ha_state()
