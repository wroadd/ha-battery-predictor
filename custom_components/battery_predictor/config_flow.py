"""Config flow for Battery Predictor integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_HISTORY_DAYS,
    CONF_LOW_BATTERY_THRESHOLD,
    CONF_SCAN_INTERVAL,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_LOW_BATTERY_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_HISTORY_DAYS,
    MIN_HISTORY_DAYS,
)


class BatteryPredictorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Battery Predictor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Only allow one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="Battery Predictor",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                    vol.Required(
                        CONF_HISTORY_DAYS, default=DEFAULT_HISTORY_DAYS
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_HISTORY_DAYS, max=MAX_HISTORY_DAYS),
                    ),
                    vol.Required(
                        CONF_LOW_BATTERY_THRESHOLD,
                        default=DEFAULT_LOW_BATTERY_THRESHOLD,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> BatteryPredictorOptionsFlow:
        """Get the options flow for this handler."""
        return BatteryPredictorOptionsFlow(config_entry)


class BatteryPredictorOptionsFlow(OptionsFlow):
    """Handle options flow for Battery Predictor."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                    vol.Required(
                        CONF_HISTORY_DAYS,
                        default=current.get(
                            CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_HISTORY_DAYS, max=MAX_HISTORY_DAYS),
                    ),
                    vol.Required(
                        CONF_LOW_BATTERY_THRESHOLD,
                        default=current.get(
                            CONF_LOW_BATTERY_THRESHOLD,
                            DEFAULT_LOW_BATTERY_THRESHOLD,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
                }
            ),
        )
