"""Sensor platform for Battery Predictor."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTRIBUTION,
    DOMAIN,
    SENSOR_BATTERY_HEALTH,
    SENSOR_DAYS_UNTIL_EMPTY,
)
from .coordinator import BatteryPrediction, BatteryPredictorCoordinator, BatteryPredictorData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Battery Predictor sensors from a config entry."""
    coordinator: BatteryPredictorCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Track which entities we've already created sensors for
    tracked: set[str] = set()

    @callback
    def _async_add_new_entities() -> None:
        """Add sensors for newly discovered battery entities."""
        if coordinator.data is None:
            return

        new_entities: list[SensorEntity] = []
        for entity_id, prediction in coordinator.data.predictions.items():
            if entity_id not in tracked:
                tracked.add(entity_id)
                new_entities.append(
                    BatteryDaysUntilEmptySensor(coordinator, entity_id, prediction)
                )
                new_entities.append(
                    BatteryHealthSensor(coordinator, entity_id, prediction)
                )

        if new_entities:
            async_add_entities(new_entities)

    # Add initial entities
    _async_add_new_entities()

    # Listen for coordinator updates to add new entities
    config_entry.async_on_unload(
        coordinator.async_add_listener(_async_add_new_entities)
    )


def _make_unique_id(entity_id: str, sensor_type: str) -> str:
    """Create a unique ID for a sensor."""
    # sensor.living_room_battery → living_room_battery
    base = entity_id.replace("sensor.", "").replace("binary_sensor.", "")
    return f"{DOMAIN}_{base}_{sensor_type}"


def _make_device_name(prediction: BatteryPrediction) -> str:
    """Create a clean device name."""
    name = prediction.friendly_name
    # Strip common suffixes
    for suffix in (" Battery", " battery", " Battery Level", " battery level"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


class BatteryDaysUntilEmptySensor(
    CoordinatorEntity[BatteryPredictorCoordinator], SensorEntity
):
    """Sensor showing estimated days until battery is empty."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_native_unit_of_measurement = "days"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-clock-outline"

    def __init__(
        self,
        coordinator: BatteryPredictorCoordinator,
        source_entity_id: str,
        prediction: BatteryPrediction,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._source_entity_id = source_entity_id
        self._attr_unique_id = _make_unique_id(
            source_entity_id, SENSOR_DAYS_UNTIL_EMPTY
        )
        device_name = _make_device_name(prediction)
        self._attr_name = f"{device_name} Days Until Empty"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        prediction = self._get_prediction()
        if prediction is None or prediction.days_until_empty is None:
            return None
        return round(prediction.days_until_empty, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        prediction = self._get_prediction()
        if prediction is None:
            return {}

        attrs: dict[str, Any] = {
            "source_entity": self._source_entity_id,
            "current_level": prediction.current_level,
            "fit_type": prediction.fit_type,
            "r_squared": round(prediction.r_squared, 4) if prediction.r_squared else None,
            "drain_rate_per_day": (
                round(prediction.drain_rate_per_day, 3)
                if prediction.drain_rate_per_day is not None
                else None
            ),
            "data_points": prediction.data_points,
            "is_stale": prediction.is_stale,
            "is_stepped": prediction.is_stepped,
        }

        if prediction.estimated_empty_date:
            attrs["estimated_empty_date"] = prediction.estimated_empty_date.isoformat()

        if prediction.last_updated:
            attrs["last_data_point"] = prediction.last_updated.isoformat()

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._get_prediction() is not None

    def _get_prediction(self) -> BatteryPrediction | None:
        """Get the prediction for this source entity."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.predictions.get(self._source_entity_id)


class BatteryHealthSensor(
    CoordinatorEntity[BatteryPredictorCoordinator], SensorEntity
):
    """Sensor showing battery health status."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["good", "fair", "poor", "critical", "unknown", "stale"]
    _attr_icon = "mdi:battery-heart-variant"

    def __init__(
        self,
        coordinator: BatteryPredictorCoordinator,
        source_entity_id: str,
        prediction: BatteryPrediction,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._source_entity_id = source_entity_id
        self._attr_unique_id = _make_unique_id(
            source_entity_id, SENSOR_BATTERY_HEALTH
        )
        device_name = _make_device_name(prediction)
        self._attr_name = f"{device_name} Battery Health"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        prediction = self._get_prediction()
        if prediction is None:
            return None
        return prediction.health

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        prediction = self._get_prediction()
        if prediction is None:
            return {}
        return {
            "source_entity": self._source_entity_id,
            "current_level": prediction.current_level,
            "days_until_empty": (
                round(prediction.days_until_empty, 1)
                if prediction.days_until_empty is not None
                else None
            ),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._get_prediction() is not None

    def _get_prediction(self) -> BatteryPrediction | None:
        """Get the prediction for this source entity."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.predictions.get(self._source_entity_id)
