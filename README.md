# HA-Dash

HA-Dash is a Pico-powered physical dashboard for Home Assistant. It connects over Wi‑Fi and interacts with Home Assistant through a lightweight API abstraction, enabling tactile controls and GPIO-driven events for your smart home.

## Features

- Raspberry Pi Pico-based physical dashboard
- Wi‑Fi connectivity for Home Assistant API access - see [Onboard status LED](#onboard-status-led)
- Async event loop for responsive, non-blocking IO
- Extensible `ha_api` abstraction for Home Assistant actions
- WebSocket event stream for HA `state_changed` updates
- Core `ha_dash` class for button watchers and other GPIO event handlers
- **Virtual dashboard pages** – map the same physical buttons and LEDs to different Home Assistant entities
- JSON-based configuration for physical layout and entity mappings
- Simple network configuration via `src/config.py`
- Web server for configuration management - under development

## Virtual Dashboard Pages

HA-Dash supports **virtual dashboard pages** that let you map the same physical buttons and LEDs to different Home Assistant entities. For example, one button can toggle your office light on page 1 and your bedroom light on page 2. You can navigate between pages using a designated "next dashboard" button.

Each virtual page maintains its own state, so when you switch pages, the physical LEDs instantly reflect the state of the entities mapped to that page. This enables a single physical dashboard to control many entities without needing a button for each one.

### Configuration

Dashboard configuration is defined in `src/dashboard_config.json`, which includes:

- **Physical layout**: Define your LEDs and buttons with their GPIO pin assignments
- **Pages**: Create multiple virtual dashboard pages, each with its own entity mappings
- **Mappings**: Map physical components (buttons/LEDs) to Home Assistant entities and actions

Example configuration:

```json
{
  "physical_layout": {
    "leds": [
      {"id": "led1", "name": "LED 1", "pin": 14}
    ],
    "buttons": [
      {"id": "btn1", "name": "Button 1", "pin": 15},
      {"id": "btn_next", "name": "Next Dashboard", "pin": 0}
    ]
  },
  "pages": [
    {
      "name": "office",
      "description": "Office dashboard",
      "mappings": [
        {"component_id": "led1", "entity_id": "light.office"},
        {"component_id": "btn1", "action": "toggle_entity", "entity_id": "light.office"},
        {"component_id": "btn_next", "action": "next_dashboard"}
      ]
    },
    {
      "name": "bedroom",
      "description": "Bedroom dashboard",
      "mappings": [
        {"component_id": "led1", "entity_id": "light.bedroom"},
        {"component_id": "btn1", "action": "toggle_entity", "entity_id": "light.bedroom"},
        {"component_id": "btn_next", "action": "next_dashboard"}
      ]
    }
  ],
  "default_page": "office"
}
```

In this example, `btn1` toggles the office light on the first page and the bedroom light on the second page. The `btn_next` button cycles through available pages.

## Developers

The codebase is structured around an async loop that drives IO without blocking. Home Assistant interactions are abstracted through an extensible `ha_api` layer, which keeps device logic decoupled from API specifics. The core `ha_dash` class provides registration and handling for button watchers and other GPIO events, which then call the abstracted API methods.

## Configuration

### Web based configuration

For now only the framework exists, however you can navigate to http://<ip/name-of-pico>:80 and see a test page.

### Home Assistant Token

To connect HA-Dash to your Home Assistant instance:

1. In Home Assistant, open your user profile.
2. Scroll to **Long-Lived Access Tokens** and create a new token.
3. Copy the token value into `src/config.py` for the API token field.

### Dashboard Setup

Entity and pin mappings are configured in `src/dashboard_config.json`:

1. **Define physical layout**: Specify your LEDs and buttons with GPIO pin numbers
2. **Create virtual pages**: Set up one or more dashboard pages
3. **Map entities**: For each page, map your physical components to Home Assistant entity IDs

To find entity IDs:
- Go to **Settings → Devices & Services** (or **Developer Tools → States**) in Home Assistant
- Find your target device and copy its entity ID (e.g., `light.kitchen` or `switch.fan`)
- Add the entity ID to the appropriate mapping in `dashboard_config.json`

## Pico Setup

1. Install MicroPython on the Pico W / Pico 2 W.
2. Configure Wi‑Fi credentials and Home Assistant URL/token in `src/config.py`.
3. Configure your physical layout and entity mappings in `src/dashboard_config.json`.
4. Copy the `src/` files to the device (for example, using Thonny or mpremote).
5. Reset the Pico to start the dashboard.

## Hardware Sourcing

- Raspberry Pi Pico W: https://shop.pimoroni.com/products/raspberry-pi-pico-w
- Raspberry Pi Pico 2 W: https://shop.pimoroni.com/products/raspberry-pi-pico-2-w

## Onboard status LED

The LED on the Pico W board is used to give feedback around network connectivity if you are not able to connect to the terminal output for logs.

- 1 flash at 2 Hz: successful connection
- 2 flashes at 2 Hz: failed connection
- Constant 4Hz flash: in backoff period before retrying connection
- No LED output: normal operation