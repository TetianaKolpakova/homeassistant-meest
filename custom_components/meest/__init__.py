"""Unofficial Meest parcel integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import MeestCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = MeestCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Token-data updates must not reload; only actual options changes do."""
    coordinator = entry.runtime_data
    from datetime import timedelta

    from .const import CONF_B2B, CONF_INTERVAL, DEFAULT_INTERVAL

    interval = timedelta(minutes=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL))
    business = entry.options.get(CONF_B2B, False)
    if (
        coordinator.update_interval != interval
        or getattr(coordinator, "business_option", False) != business
    ):
        await hass.config_entries.async_reload(entry.entry_id)
