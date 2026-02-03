# HA-Dash

HA-Dash is a Pico-powered physical dashboard for Home Assistant. It connects over Wi‑Fi and interacts with Home Assistant through a lightweight API abstraction, enabling tactile controls and GPIO-driven events for your smart home.

## Features

- Raspberry Pi Pico-based physical dashboard
- Wi‑Fi connectivity for Home Assistant API access - see [Onboard status LED](#onboard-status-led)
- Async event loop for responsive, non-blocking IO
- Extensible `ha_api` abstraction for Home Assistant actions
- Core `ha_dash` class for button watchers and other GPIO event handlers
- Simple configuration via `src/config.py`

## Developers

The codebase is structured around an async loop that drives IO without blocking. Home Assistant interactions are abstracted through an extensible `ha_api` layer, which keeps device logic decoupled from API specifics. The core `ha_dash` class provides registration and handling for button watchers and other GPIO events, which then call the abstracted API methods.

## PoC Config: Token and Entity ID

To populate the PoC config file with a Home Assistant token and entity ID:

1. In Home Assistant, open your user profile.
2. Scroll to **Long-Lived Access Tokens** and create a new token.
3. Copy the token value into the PoC config field for the API token.
4. Find the target device in **Settings → Devices & Services** (or **Developer Tools → States**).
5. Copy the entity ID (for example, `light.kitchen` or `switch.fan`).
6. Paste the entity ID into the PoC config field for the entity.

## Pico Setup

1. Install MicroPython on the Pico W / Pico 2 W.
2. Configure Wi‑Fi credentials and Home Assistant settings in `src/config.py`.
3. Copy the `src/` files to the device (for example, using Thonny or mpremote).
4. Reset the Pico to start the dashboard.

## Hardware Sourcing

- Raspberry Pi Pico W: https://shop.pimoroni.com/products/raspberry-pi-pico-w
- Raspberry Pi Pico 2 W: https://shop.pimoroni.com/products/raspberry-pi-pico-2-w

## Onboard status LED

The LED on the Pico W board is used to give feedback around network connectivity if you are not able to connect to the terminal output for logs.

- 1 flash at 2 Hz: successful connection
- 2 flashes at 2 Hz: failed connection
- Constant 4Hz flash: in backoff period before retrying connection
- No LED output: normal operation