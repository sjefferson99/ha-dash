from lib.ulogging import uLogger
from config import BUTTON1_PIN, BUTTON1_ENTITY
from lib.networking import WirelessNetwork
from lib.button import Button
from lib.ha_api import HomeAssistantAPI
from asyncio import sleep_ms, Event, create_task, get_event_loop
import lib.uaiohttpclient as httpclient

class HADash:
    def __init__(self):
        self.logger = uLogger("HADash")
        self.logger.info("HADash initialized")
        self.button1_event = Event()
        self.button1 = Button(BUTTON1_PIN, "Button1", self.button1_event)
        self.wireless = WirelessNetwork()
        self.ha_api = HomeAssistantAPI(self.wireless)

    def startup(self):
        self.logger.info("HADash is starting up...")
        self.wireless.startup()
        self.configure_buttons()
        asyncio_loop = get_event_loop()
        asyncio_loop.run_forever()

    def configure_buttons(self):
        self.logger.info("Configuring buttons...")
        create_task(self.button1.wait_for_press())
        create_task(self.monitor_buttons())

    async def monitor_buttons(self):
        self.logger.info("Starting button monitor...")
        while True:
            await sleep_ms(20)
            if self.button1_event.is_set():
                self.logger.info(f"{self.button1.get_name()} was pressed!")
                await self.button1_action()
                self.button1_event.clear()

    async def button1_action(self):
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
        