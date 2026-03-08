"""Battery Predictor integration for Home Assistant.

Monitors battery-powered devices and predicts when batteries will need replacement
using linear and exponential curve fitting on historical data.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_HISTORY_DAYS,
    CONF_LOW_BATTERY_THRESHOLD,
    CONF_SCAN_INTERVAL,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_LOW_BATTERY_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_RECALCULATE,
)
from .coordinator import BatteryPredictorCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Battery Predictor from a config entry."""
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    history_days = entry.data.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
    low_threshold = entry.data.get(
        CONF_LOW_BATTERY_THRESHOLD, DEFAULT_LOW_BATTERY_THRESHOLD
    )

    coordinator = BatteryPredictorCoordinator(
        hass,
        scan_interval_hours=scan_interval,
        history_days=history_days,
        low_battery_threshold=low_threshold,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register recalculate service
    async def handle_recalculate(call: ServiceCall) -> None:
        """Handle the recalculate service call."""
        _LOGGER.info("Recalculating battery predictions")
        for coordinator in hass.data[DOMAIN].values():
            if isinstance(coordinator, BatteryPredictorCoordinator):
                await coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_RECALCULATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RECALCULATE,
            handle_recalculate,
            schema=vol.Schema({}),
        )

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        # Remove service if no more entries
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_RECALCULATE)
            hass.data.pop(DOMAIN)

    return unload_ok
