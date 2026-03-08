"""DataUpdateCoordinator for Battery Predictor."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import state_changes_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    BATTERY_REPLACEMENT_JUMP,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_LOW_BATTERY_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_LOW_BATTERY,
    HEALTH_CRITICAL,
    HEALTH_FAIR,
    HEALTH_GOOD,
    HEALTH_POOR,
    HEALTH_STALE,
    HEALTH_UNKNOWN,
    MIN_DATA_POINTS,
    R_SQUARED_IMPROVEMENT_THRESHOLD,
    STALE_HOURS,
    STEPPED_SENSOR_LEVELS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class BatteryPrediction:
    """Prediction data for a single battery."""

    entity_id: str
    friendly_name: str
    current_level: float | None = None
    days_until_empty: float | None = None
    health: str = HEALTH_UNKNOWN
    fit_type: str = "unknown"
    r_squared: float = 0.0
    drain_rate_per_day: float | None = None
    last_updated: datetime | None = None
    is_stale: bool = False
    is_stepped: bool = False
    data_points: int = 0
    estimated_empty_date: datetime | None = None


@dataclass
class BatteryPredictorData:
    """Data class for coordinator."""

    predictions: dict[str, BatteryPrediction] = field(default_factory=dict)
    last_full_update: datetime | None = None


class BatteryPredictorCoordinator(DataUpdateCoordinator[BatteryPredictorData]):
    """Coordinator to manage battery predictions."""

    def __init__(
        self,
        hass: HomeAssistant,
        scan_interval_hours: int = DEFAULT_SCAN_INTERVAL,
        history_days: int = DEFAULT_HISTORY_DAYS,
        low_battery_threshold: int = DEFAULT_LOW_BATTERY_THRESHOLD,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=scan_interval_hours),
        )
        self.history_days = history_days
        self.low_battery_threshold = low_battery_threshold
        self._previous_alerts: set[str] = set()

    async def _async_update_data(self) -> BatteryPredictorData:
        """Fetch and process battery data."""
        battery_entities = self._find_battery_entities()
        if not battery_entities:
            _LOGGER.debug("No battery entities found")
            return BatteryPredictorData()

        predictions: dict[str, BatteryPrediction] = {}
        now = dt_util.utcnow()
        start_time = now - timedelta(days=self.history_days)

        # Fetch history from recorder
        history_data = await get_instance(self.hass).async_add_executor_job(
            state_changes_during_period,
            self.hass,
            start_time,
            now,
            list(battery_entities.keys()),
        )

        for entity_id, friendly_name in battery_entities.items():
            try:
                states = history_data.get(entity_id, [])
                prediction = self._process_entity(
                    entity_id, friendly_name, states, now
                )
                predictions[entity_id] = prediction

                # Fire event if threshold crossed (only once per entity)
                if (
                    prediction.days_until_empty is not None
                    and prediction.days_until_empty < self.low_battery_threshold
                    and not prediction.is_stale
                    and entity_id not in self._previous_alerts
                ):
                    self._previous_alerts.add(entity_id)
                    self.hass.bus.async_fire(
                        EVENT_LOW_BATTERY,
                        {
                            "entity_id": entity_id,
                            "friendly_name": friendly_name,
                            "days_until_empty": round(prediction.days_until_empty, 1),
                            "current_level": prediction.current_level,
                            "health": prediction.health,
                        },
                    )
                elif (
                    prediction.days_until_empty is not None
                    and prediction.days_until_empty >= self.low_battery_threshold
                    and entity_id in self._previous_alerts
                ):
                    # Reset alert if battery recovered
                    self._previous_alerts.discard(entity_id)

            except Exception:
                _LOGGER.exception("Error processing %s", entity_id)
                predictions[entity_id] = BatteryPrediction(
                    entity_id=entity_id,
                    friendly_name=friendly_name,
                    health=HEALTH_UNKNOWN,
                )

        return BatteryPredictorData(predictions=predictions, last_full_update=now)

    def _find_battery_entities(self) -> dict[str, str]:
        """Find all battery level entities."""
        battery_entities: dict[str, str] = {}
        states = self.hass.states.async_all("sensor")

        for state in states:
            # Check device_class or entity naming
            device_class = state.attributes.get("device_class", "")
            unit = state.attributes.get("unit_of_measurement", "")

            if device_class == "battery" or (
                "battery" in state.entity_id
                and unit == "%"
            ):
                # Validate the state is numeric
                try:
                    val = float(state.state)
                    if 0 <= val <= 100:
                        friendly_name = state.attributes.get(
                            "friendly_name", state.entity_id
                        )
                        battery_entities[state.entity_id] = friendly_name
                except (ValueError, TypeError):
                    continue

        return battery_entities

    def _process_entity(
        self,
        entity_id: str,
        friendly_name: str,
        states: list,
        now: datetime,
    ) -> BatteryPrediction:
        """Process a single entity's history into a prediction."""
        prediction = BatteryPrediction(
            entity_id=entity_id,
            friendly_name=friendly_name,
        )

        # Extract valid data points (timestamp, level)
        data_points: list[tuple[float, float]] = []
        for state in states:
            try:
                level = float(state.state)
                if 0 <= level <= 100:
                    ts = state.last_changed.timestamp()
                    data_points.append((ts, level))
            except (ValueError, TypeError, AttributeError):
                continue

        if not data_points:
            # Try current state
            current_state = self.hass.states.get(entity_id)
            if current_state:
                try:
                    prediction.current_level = float(current_state.state)
                except (ValueError, TypeError):
                    pass
            return prediction

        # Sort by timestamp
        data_points.sort(key=lambda x: x[0])

        # Detect battery replacement (large upward jump) and keep only post-replacement
        data_points = self._handle_replacements(data_points)

        prediction.current_level = data_points[-1][1]
        prediction.data_points = len(data_points)
        prediction.last_updated = datetime.fromtimestamp(
            data_points[-1][0], tz=now.tzinfo
        )

        # Check staleness
        last_ts = data_points[-1][0]
        hours_since = (now.timestamp() - last_ts) / 3600
        if hours_since > STALE_HOURS:
            prediction.is_stale = True
            prediction.health = HEALTH_STALE
            return prediction

        # Check if stepped sensor
        unique_levels = {p[1] for p in data_points}
        prediction.is_stepped = unique_levels.issubset(STEPPED_SENSOR_LEVELS) and len(
            unique_levels
        ) <= 5

        if prediction.is_stepped:
            prediction = self._fit_stepped(data_points, prediction, now)
        elif len(data_points) >= MIN_DATA_POINTS:
            prediction = self._fit_curve(data_points, prediction, now)
        else:
            # Not enough data for fitting
            prediction.health = HEALTH_UNKNOWN

        return prediction

    def _handle_replacements(
        self, data_points: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Detect battery replacements and return data after last replacement."""
        last_replacement_idx = 0

        for i in range(1, len(data_points)):
            prev_level = data_points[i - 1][1]
            curr_level = data_points[i][1]
            jump = curr_level - prev_level

            if jump >= BATTERY_REPLACEMENT_JUMP and prev_level < 60:
                last_replacement_idx = i

        return data_points[last_replacement_idx:]

    def _fit_stepped(
        self,
        data_points: list[tuple[float, float]],
        prediction: BatteryPrediction,
        now: datetime,
    ) -> BatteryPrediction:
        """Handle stepped sensors (e.g., 100/50/0)."""
        # Find transitions between steps
        transitions: list[tuple[float, float, float, float]] = []
        for i in range(1, len(data_points)):
            if data_points[i][1] != data_points[i - 1][1]:
                transitions.append(
                    (
                        data_points[i - 1][0],
                        data_points[i - 1][1],
                        data_points[i][0],
                        data_points[i][1],
                    )
                )

        if not transitions:
            # No transitions observed, can't predict
            prediction.fit_type = "stepped_insufficient"
            prediction.health = HEALTH_UNKNOWN
            return prediction

        # Calculate average drain rate from transitions
        total_drop = 0.0
        total_time = 0.0
        for t_start, l_start, t_end, l_end in transitions:
            drop = l_start - l_end
            duration = t_end - t_start
            if drop > 0 and duration > 0:
                total_drop += drop
                total_time += duration

        if total_drop <= 0 or total_time <= 0:
            prediction.fit_type = "stepped_no_drain"
            prediction.health = HEALTH_UNKNOWN
            return prediction

        # Rate in % per day
        drain_rate = (total_drop / total_time) * 86400
        prediction.drain_rate_per_day = drain_rate
        prediction.fit_type = "stepped"

        current_level = prediction.current_level or 0
        if drain_rate > 0:
            days = current_level / drain_rate
            prediction.days_until_empty = days
            prediction.estimated_empty_date = now + timedelta(days=days)

        prediction.health = self._calculate_health(prediction.days_until_empty)
        return prediction

    def _fit_curve(
        self,
        data_points: list[tuple[float, float]],
        prediction: BatteryPrediction,
        now: datetime,
    ) -> BatteryPrediction:
        """Fit linear and exponential curves, pick the best."""
        # Normalize timestamps to days from first point
        t0 = data_points[0][0]
        days = [(p[0] - t0) / 86400 for p in data_points]
        levels = [p[1] for p in data_points]

        n = len(days)

        # Linear regression: level = a * day + b
        lin_slope, lin_intercept, lin_r2 = self._linear_regression(days, levels)

        # Exponential fit: level = A * exp(k * day)
        # Use log-linear regression: ln(level) = ln(A) + k * day
        exp_r2 = -1.0
        exp_a = 0.0
        exp_k = 0.0

        log_levels = []
        valid_days_exp = []
        for d, lev in zip(days, levels):
            if lev > 0:
                log_levels.append(math.log(lev))
                valid_days_exp.append(d)

        if len(log_levels) >= MIN_DATA_POINTS:
            k_slope, ln_a, exp_r2_log = self._linear_regression(
                valid_days_exp, log_levels
            )
            exp_k = k_slope
            exp_a = math.exp(ln_a)

            # Calculate actual R² for exponential on original scale
            exp_predictions = []
            for d in days:
                try:
                    exp_predictions.append(exp_a * math.exp(exp_k * d))
                except OverflowError:
                    exp_predictions.append(float("inf"))

            ss_res = sum((lev - pred) ** 2 for lev, pred in zip(levels, exp_predictions))
            mean_level = sum(levels) / n
            ss_tot = sum((lev - mean_level) ** 2 for lev in levels)
            exp_r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Choose best fit
        use_exponential = (
            exp_r2 > lin_r2 + R_SQUARED_IMPROVEMENT_THRESHOLD
            and exp_k < 0  # must be decaying
        )

        # Current time in days from t0
        now_day = (now.timestamp() - t0) / 86400

        if use_exponential and exp_k < 0:
            prediction.fit_type = "exponential"
            prediction.r_squared = exp_r2

            # Solve A * exp(k * d) = 0 → never reaches 0
            # Use threshold of 1% instead
            # A * exp(k * d) = 1 → d = (ln(1) - ln(A)) / k = -ln(A) / k
            if exp_a > 1:
                d_empty = -math.log(exp_a) / exp_k
                prediction.days_until_empty = max(0, d_empty - now_day)
            else:
                prediction.days_until_empty = None

            # Drain rate: derivative at current point
            try:
                current_pred = exp_a * math.exp(exp_k * now_day)
                prediction.drain_rate_per_day = abs(exp_k * current_pred)
            except OverflowError:
                prediction.drain_rate_per_day = None

        else:
            prediction.fit_type = "linear"
            prediction.r_squared = lin_r2

            if lin_slope < 0:
                # level = slope * day + intercept = 0
                # day = -intercept / slope
                d_empty = -lin_intercept / lin_slope
                prediction.days_until_empty = max(0, d_empty - now_day)
                prediction.drain_rate_per_day = abs(lin_slope)
            elif lin_slope == 0:
                prediction.days_until_empty = None  # not draining
                prediction.drain_rate_per_day = 0
            else:
                # Battery level increasing (charging or noise)
                prediction.days_until_empty = None
                prediction.drain_rate_per_day = 0

        if prediction.days_until_empty is not None:
            prediction.estimated_empty_date = now + timedelta(
                days=prediction.days_until_empty
            )

        prediction.health = self._calculate_health(prediction.days_until_empty)
        return prediction

    @staticmethod
    def _linear_regression(
        x: list[float], y: list[float]
    ) -> tuple[float, float, float]:
        """Simple linear regression returning slope, intercept, R²."""
        n = len(x)
        if n < 2:
            return 0.0, 0.0, 0.0

        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return 0.0, sum_y / n if n > 0 else 0.0, 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n

        # R²
        mean_y = sum_y / n
        ss_tot = sum((yi - mean_y) ** 2 for yi in y)
        ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))

        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        return slope, intercept, r_squared

    @staticmethod
    def _calculate_health(days_until_empty: float | None) -> str:
        """Calculate health category from days until empty."""
        if days_until_empty is None:
            return HEALTH_UNKNOWN

        if days_until_empty > 90:
            return HEALTH_GOOD
        if days_until_empty > 30:
            return HEALTH_FAIR
        if days_until_empty > 7:
            return HEALTH_POOR
        return HEALTH_CRITICAL
