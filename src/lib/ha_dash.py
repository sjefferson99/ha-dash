from lib.ulogging import uLogger
from config import BUTTON1_PIN, BUTTON1_ENTITY, LED1_PIN, LED1_ENTITY
from lib.networking import WirelessNetwork
from lib.button import Button
from lib.ha_api import HomeAssistantAPI
from lib.ha_websocket import HomeAssistantWebSocket
from asyncio import sleep_ms, Event, create_task, get_event_loop
from lib.utils import StatusLED

class HADash:
    """Main application class for the HA hardware dashboard."""
    def __init__(self) -> None:
        """Initialize buttons, networking, and HA API clients."""
        self.logger = uLogger("HADash")
        self.logger.info("HADash initialized")
        self.button1_event = Event()
        self.button1 = Button(BUTTON1_PIN, "Button1", self.button1_event)
        self.status_led = StatusLED()
        self._flash_task = None
        self.wireless = WirelessNetwork()
        self.ha_api = HomeAssistantAPI(self.wireless)
        self.ha_ws = HomeAssistantWebSocket(self.wireless)

    def startup(self) -> None:
        """Start background tasks and enter the event loop."""
        self.logger.info("HADash is starting up...")
        self.wireless.startup()
        self.configure_buttons()
        asyncio_loop = get_event_loop()
        asyncio_loop.run_forever()

    def configure_buttons(self) -> None:
        """Create background tasks for buttons and HA event monitor."""
        self.logger.info("Configuring buttons...")
        create_task(self.button1.wait_for_press())
        create_task(self.monitor_buttons())
        create_task(self.monitor_ha_state_changes())

    async def monitor_ha_state_changes(self) -> None:
        """Listen for HA state_changed events via WebSocket."""
        self.logger.info("Starting HA WebSocket monitor...")
        await self.ha_ws.listen_forever(self.handle_ha_event, event_type="state_changed")

    async def handle_ha_event(self, message: dict) -> None:
        """Handle a Home Assistant event message."""
        if message.get("type") != "event":
            return
        event = message.get("event", {})
        if event.get("event_type") != "state_changed":
            return
        data = event.get("data", {})
        entity_id = data.get("entity_id")
        new_state = data.get("new_state", {})
        state_value = None
        if isinstance(new_state, dict):
            state_value = new_state.get("state")

        if entity_id:
            if state_value is not None:
                self.logger.info(f"state_changed: {entity_id} -> {state_value}")
            else:
                self.logger.info(f"state_changed: {entity_id}")
            self.trigger_status_flash()

    def trigger_status_flash(self) -> None:
        """Trigger a single LED flash without overlapping tasks."""
        if self._flash_task is None or self._flash_task.done():
            self._flash_task = create_task(self.status_led.async_flash(1, 4))

    async def monitor_buttons(self) -> None:
        """Watch for button events and dispatch actions."""
        self.logger.info("Starting button monitor...")
        while True:
            await sleep_ms(20)
            if self.button1_event.is_set():
                self.logger.info(f"{self.button1.get_name()} was pressed!")
                await self.button1_action()
                self.button1_event.clear()

    async def button1_action(self) -> None:
        """Toggle the configured Home Assistant light and log its new state."""
        self.logger.info("Button 1 action: Toggling HA light...")
        try:
            # Toggle the light - service calls return array of states after action
            result = await self.ha_api.toggle_light(BUTTON1_ENTITY)
            self.logger.info(f"Light {BUTTON1_ENTITY} toggled successfully")
            
            # The result array contains the new states, extract if available
            if isinstance(result, list) and len(result) > 0:
                current_state = result[0].get('state', 'toggled')
                self.logger.info(f"Light is now: {current_state}")
            else:
                self.logger.info("Light toggled (state not returned)")
            
        except Exception as e:
            self.logger.error(f"Failed to toggle light: {e}")
        