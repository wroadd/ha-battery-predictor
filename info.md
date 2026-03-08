## Battery Predictor

Predicts when your battery-powered devices will need new batteries by analyzing historical drain patterns.

### Features
- 🔋 Automatic discovery of all battery sensors
- 📈 Smart curve fitting (linear + exponential)
- ⏰ Days-until-empty prediction per device
- 🏥 Battery health status (good/fair/poor/critical)
- 🔔 Event firing when batteries are running low
- 🔄 Handles battery replacements, stepped sensors, and stale devices

### Sensors Created
For each battery device:
- `sensor.{device}_days_until_empty` — estimated days remaining
- `sensor.{device}_battery_health` — health status enum

### Services
- `battery_predictor.recalculate` — force refresh all predictions
