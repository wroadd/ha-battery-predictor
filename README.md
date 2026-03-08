# 🔋 Battery Predictor for Home Assistant

[![HACS Validation](https://github.com/wroadd/ha-battery-predictor/actions/workflows/hacs.yml/badge.svg)](https://github.com/wroadd/ha-battery-predictor/actions/workflows/hacs.yml)
[![Hassfest Validation](https://github.com/wroadd/ha-battery-predictor/actions/workflows/hassfest.yml/badge.svg)](https://github.com/wroadd/ha-battery-predictor/actions/workflows/hassfest.yml)

Predicts when your battery-powered devices will need new batteries by analyzing historical drain patterns from the Home Assistant recorder.

## Features

- **Automatic discovery** — finds all battery sensors (`device_class: battery`) automatically
- **Smart curve fitting** — linear regression as baseline, switches to exponential decay when it fits significantly better (R² improvement > 5%)
- **Two sensors per device:**
  - `sensor.{device}_days_until_empty` — estimated days until battery is depleted
  - `sensor.{device}_battery_health` — health category (good / fair / poor / critical / stale / unknown)
- **Edge case handling:**
  - 🔄 **Battery replacement detection** — large upward jumps reset the curve
  - 📊 **Stepped sensors** (100%/50%/0%) — uses time-between-steps instead of continuous fitting
  - 📡 **Offline devices** — marked as "stale" after 48h without data
- **Events** — fires `battery_predictor_low_battery` when estimated days < threshold
- **Services** — `battery_predictor.recalculate` to force-refresh all predictions
- **No external dependencies** — uses only Python stdlib and HA helpers

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/wroadd/ha-battery-predictor` as an **Integration**
4. Install "Battery Predictor"
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration → Battery Predictor**

### Manual

1. Copy `custom_components/battery_predictor/` to your `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via UI

## Configuration

All configuration is done through the UI:

| Option | Default | Description |
|--------|---------|-------------|
| Scan interval | 6 hours | How often to recalculate predictions |
| History lookback | 30 days | How many days of history to analyze |
| Low battery threshold | 14 days | Fire alert event when below this |

## Sensor Attributes

### Days Until Empty

| Attribute | Description |
|-----------|-------------|
| `source_entity` | The original battery sensor entity ID |
| `current_level` | Current battery percentage |
| `fit_type` | Curve type used: `linear`, `exponential`, or `stepped` |
| `r_squared` | Goodness of fit (0-1, higher is better) |
| `drain_rate_per_day` | Estimated % drain per day |
| `estimated_empty_date` | ISO datetime when battery is predicted to be empty |
| `data_points` | Number of historical data points used |
| `is_stale` | Whether the device hasn't reported recently |
| `is_stepped` | Whether this is a stepped sensor (e.g., 100/50/0) |

### Battery Health

| State | Meaning |
|-------|---------|
| `good` | > 90 days remaining |
| `fair` | 30-90 days remaining |
| `poor` | 7-30 days remaining |
| `critical` | < 7 days remaining |
| `stale` | Device offline > 48h |
| `unknown` | Insufficient data |

## Automations

### Low battery notification

```yaml
automation:
  - alias: "Battery Predictor Alert"
    trigger:
      - platform: event
        event_type: battery_predictor_low_battery
    action:
      - service: notify.mobile_app
        data:
          title: "🔋 Low Battery Warning"
          message: >
            {{ trigger.event.data.friendly_name }} has approximately
            {{ trigger.event.data.days_until_empty }} days of battery remaining.
```

### Group by replacement urgency

```yaml
template:
  - sensor:
      - name: "Batteries Needing Replacement Soon"
        state: >
          {{ states.sensor
            | selectattr('attributes.source_entity', 'defined')
            | selectattr('entity_id', 'search', 'days_until_empty')
            | selectattr('state', 'is_number')
            | selectattr('state', 'lt', '14')
            | list | count }}
```

## Requirements

- Home Assistant 2024.1.0 or newer
- Recorder component enabled (default in HA)
- Battery sensors with `device_class: battery` or `battery` in entity ID

## License

MIT — see [LICENSE](LICENSE)
