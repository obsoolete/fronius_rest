"""Switch platform for the Fronius Gen24 REST integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_EXPORT_ENABLED, DATA_PV_ENABLED, DOMAIN
from .coordinator import FroniusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fronius Gen24 switch entities."""
    coordinator: FroniusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FroniusPVEnabledSwitch(coordinator, entry),
            FroniusExportLimitationSwitch(coordinator, entry),
        ]
    )


class FroniusPVEnabledSwitch(CoordinatorEntity[FroniusCoordinator], SwitchEntity):
    """Switch that controls PV mode on both MPPT channels."""

    _attr_has_entity_name = True
    _attr_name = "PV Enabled"
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: FroniusCoordinator, entry: ConfigEntry) -> None:
        """Initialise the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_pv_enabled"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return True when both MPPT channels are enabled."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(DATA_PV_ENABLED)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable PV mode on both MPPT channels."""
        await self.coordinator.async_set_pv_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable PV mode on both MPPT channels."""
        await self.coordinator.async_set_pv_enabled(False)


class FroniusExportLimitationSwitch(CoordinatorEntity[FroniusCoordinator], SwitchEntity):
    """Switch that controls the export limitation soft-limit."""

    _attr_has_entity_name = True
    _attr_name = "Export Limitation"
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, coordinator: FroniusCoordinator, entry: ConfigEntry) -> None:
        """Initialise the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_export_limitation"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return True when the export soft-limit is enabled."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(DATA_EXPORT_ENABLED)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the export limitation."""
        await self.coordinator.async_set_export_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the export limitation."""
        await self.coordinator.async_set_export_enabled(False)
