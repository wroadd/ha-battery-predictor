"""Constants for the Battery Predictor integration."""

from typing import Final

DOMAIN: Final = "battery_predictor"

# Configuration
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_HISTORY_DAYS: Final = "history_days"
CONF_LOW_BATTERY_THRESHOLD: Final = "low_battery_threshold"
CONF_TRACKED_ENTITIES: Final = "tracked_entities"

# Defaults
DEFAULT_SCAN_INTERVAL: Final = 6  # hours
DEFAULT_HISTORY_DAYS: Final = 30
DEFAULT_LOW_BATTERY_THRESHOLD: Final = 14  # days

# Limits
MIN_HISTORY_DAYS: Final = 7
MAX_HISTORY_DAYS: Final = 90
MIN_DATA_POINTS: Final = 5

# Fitting
R_SQUARED_IMPROVEMENT_THRESHOLD: Final = 0.05  # exponential must improve by 5%
BATTERY_REPLACEMENT_JUMP: Final = 40  # % jump to detect replacement
STEPPED_SENSOR_LEVELS: Final = {0, 25, 50, 75, 100}
STALE_HOURS: Final = 48  # mark prediction stale after this many hours offline

# Events
EVENT_LOW_BATTERY: Final = "battery_predictor_low_battery"

# Services
SERVICE_RECALCULATE: Final = "recalculate"

# Sensor types
SENSOR_DAYS_UNTIL_EMPTY: Final = "days_until_empty"
SENSOR_BATTERY_HEALTH: Final = "battery_health"

# Health states
HEALTH_GOOD: Final = "good"
HEALTH_FAIR: Final = "fair"
HEALTH_POOR: Final = "poor"
HEALTH_CRITICAL: Final = "critical"
HEALTH_UNKNOWN: Final = "unknown"
HEALTH_STALE: Final = "stale"

# Attribution
ATTRIBUTION: Final = "Data provided by Battery Predictor"
