from lib.ulogging import uLogger
from lib.networking import WirelessNetwork
from lib.ha_api import HomeAssistantAPI
from lib.ha_websocket import HomeAssistantWebSocket
from asyncio import create_task, get_event_loop, sleep
from lib.utils import StatusLED
from lib.event_handler import EventHandler
from lib.dashboard_config import DashboardConfig
from lib.ha_button import HAButton
from utime import ticks_ms, ticks_diff
from config import WS_WATCHDOG_TIMEOUT_SECONDS
from http.lib.webserver import WebServer
from http.lib.ha_dash_api import HADashAPI

class HADash:
    """Main application class for the HA hardware dashboard."""
    def __init__(self) -> None:
        """Initialize buttons, networking, and HA API clients."""
        self.logger = uLogger("HADash")
        self.logger.info("HADash initialized")
        self.status_led = StatusLED()
        self._flash_task = None
        self.wireless = WirelessNetwork()
        self.ha_api = HomeAssistantAPI(self.wireless)
        self.ha_ws = HomeAssistantWebSocket(self.wireless)
        
        # Initialize event handler and dashboard pages
        self.event_handler = EventHandler(self.ha_api)
        self.physical_layout = None
        self.ha_buttons = []  # List of HAButton instances
        self._last_event_ms = ticks_ms()  # Track last event for watchdog
        self._ws_monitor_task = None  # Track websocket monitor task
        self._web_server_task = None  # Track web server task
        
        # Initialize web server and API
        self.web_server = WebServer()
        self.api = HADashAPI(self.web_server, self)
        self.api.register_routes()
        
        self._setup_pages()
    
    def _setup_pages(self) -> None:
        """Configure dashboard pages with GPIO and entity mappings."""
        try:
            # Load configuration from JSON file
            dash_config = DashboardConfig("dashboard_config.json")
            dash_config.load()
            
            # Create physical layout from config
            self.physical_layout = dash_config.create_physical_layout()
            
            # Create HAButton instances for all physical buttons BEFORE pages
            ha_buttons_dict = self._create_ha_buttons()
            
            # Create pages from configuration (will configure HAButtons for each page)
            pages = dash_config.create_pages(self.physical_layout, ha_buttons_dict)
            
            # Register all pages with the event handler
            for page in pages:
                self.event_handler.register_page(page)
            
            # Set the default page if specified
            default_page = dash_config.get_default_page()
            if default_page:
                self.event_handler.set_current_page(default_page)
            
            self.logger.info(f"Dashboard configured with {len(pages)} pages from JSON config")
            
        except Exception as e:
            self.logger.error(f"Failed to load dashboard config: {e}")
    
    def _create_ha_buttons(self) -> dict:
        """
        Create HAButton instances for all buttons in physical layout.
        
        Returns:
            Dictionary mapping component_id to HAButton instance
        """
        if not self.physical_layout:
            self.logger.warn("No physical layout available for button setup")
            return {}
        
        ha_buttons_dict = {}
        physical_buttons = self.physical_layout.get_all_buttons()
        self.logger.info(f"Creating {len(physical_buttons)} HAButton instances from physical layout")
        
        for button_component in physical_buttons:
            ha_button = HAButton(
                button_component.id,
                button_component.pin,
                button_component.name,
                self.event_handler,
                self.ha_api
            )
            ha_buttons_dict[button_component.id] = ha_button
            self.ha_buttons.append(ha_button)
        
        self.logger.info(f"Created {len(self.ha_buttons)} HAButton instances")
        return ha_buttons_dict

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
        
        # Start tasks for all HAButton instances
        for ha_button in self.ha_buttons:
            ha_button.start_tasks()
        
        self.logger.info(f"Started tasks for {len(self.ha_buttons)} buttons")
        
        # Start HA WebSocket monitor with watchdog (begins listening immediately to avoid missing events)
        self._ws_monitor_task = create_task(self._websocket_monitor_with_watchdog())
        
        # Start initial state sync (runs after WebSocket is connected)
        create_task(self.initial_state_sync())
        
        # Start watchdog to monitor websocket health
        create_task(self._websocket_watchdog())
        
        # Start web server for configuration interface
        self._web_server_task = create_task(self._start_web_server_with_recovery())

    async def _start_web_server_with_recovery(self) -> None:
        """Start web server with automatic recovery on failure."""
        attempt = 0
        retry_delay = 60  # Wait 60 seconds before retry
        
        while True:
            attempt += 1
            try:
                self.logger.info(f"Starting web server (attempt {attempt})...")
                await self._start_web_server()
                # If we get here, server stopped unexpectedly
                self.logger.warn("Web server stopped unexpectedly")
            except Exception as e:
                self.logger.error(f"Web server task failed with exception: {e}")
            
            # Wait before retry
            self.logger.info(f"Will retry web server in {retry_delay}s...")
            await sleep(retry_delay)

    async def _websocket_monitor_with_watchdog(self) -> None:
        """Listen for HA state_changed events via WebSocket with recovery wrapper."""
        attempt = 0
        while True:
            attempt += 1
            try:
                self.logger.info(f"Starting HA WebSocket monitor (attempt {attempt})...")
                await self.ha_ws.listen_forever(self.handle_ha_event, event_type="state_changed")
                # If listen_forever exits (it shouldn't), log and restart
                self.logger.error("WebSocket listen_forever unexpectedly exited, restarting...")
            except Exception as e:
                self.logger.error(f"Fatal error in WebSocket monitor: {e}")
            # Brief delay before restarting
            await sleep(2)
    
    async def _websocket_watchdog(self) -> None:
        """Monitor websocket health and restart if no events received."""
        watchdog_timeout_s = WS_WATCHDOG_TIMEOUT_SECONDS
        check_interval_s = 60  # Check every minute
        
        # Wait for initial connection before starting watchdog
        self.logger.info("Waiting for WebSocket connection before starting watchdog...")
        max_wait = 60  # Maximum 60 seconds to wait for connection
        waited = 0
        while not self.ha_ws.is_open() and waited < max_wait:
            await sleep(2)
            waited += 2
        
        if not self.ha_ws.is_open():
            self.logger.warn(f"WebSocket not open after {max_wait}s, starting watchdog anyway")

        self.logger.info(f"WebSocket watchdog started (timeout: {watchdog_timeout_s}s)")
        
        while True:
            try:
                await sleep(check_interval_s)
                
                time_since_last_event = ticks_diff(ticks_ms(), self._last_event_ms) / 1000
                
                if time_since_last_event > watchdog_timeout_s:
                    self.logger.error(f"WebSocket watchdog triggered: No events for {time_since_last_event:.0f}s")
                    self.logger.info("Forcing WebSocket restart via close...")
                    
                    try:
                        # Force close the websocket to trigger reconnect
                        await self.ha_ws.close()
                        self._last_event_ms = ticks_ms()  # Reset timer
                    except Exception as e:
                        self.logger.error(f"Error closing websocket in watchdog: {e}")
                    
                    # If monitor task is stuck, cancel and recreate it
                    if self._ws_monitor_task and not self._ws_monitor_task.done():
                        self.logger.warn("Cancelling stuck WebSocket monitor task")
                        self._ws_monitor_task.cancel()
                        try:
                            await self._ws_monitor_task
                        except Exception as e:
                            self.logger.warn(f"Error awaiting cancelled task: {e}")
                    
                    # Recreate monitor task
                    self._ws_monitor_task = create_task(self._websocket_monitor_with_watchdog())
                    self.logger.info("WebSocket monitor task recreated")
            except Exception as e:
                self.logger.error(f"Error in watchdog loop: {e}")
                # Brief delay before next check to avoid tight error loops
                await sleep(5)
    
    async def initial_state_sync(self) -> None:
        """
        Perform initial state synchronization after WebSocket is connected.
        
        This runs after the WebSocket listener starts to avoid race conditions where
        state changes could be missed during sync. Any duplicate updates from events
        received during sync are harmless.
        """
        # Wait for WebSocket to establish connection and subscription
        max_wait_seconds = 15
        wait_interval = 0.5
        elapsed = 0
        
        self.logger.info("Waiting for WebSocket connection before initial sync...")
        while not self.ha_ws.is_open() and elapsed < max_wait_seconds:
            await sleep(wait_interval)
            elapsed += wait_interval
        
        if not self.ha_ws.is_open():
            self.logger.error("WebSocket not connected after waiting, initial sync may fail")
        else:
            # Give it a bit more time to complete subscription
            await sleep(1)
            self.logger.info("WebSocket connected, starting initial state sync...")
        
        await self.event_handler.resync_all_pages()
        self.logger.info("Initial state sync complete")

    async def handle_ha_event(self, message: dict) -> None:
        """Handle a Home Assistant event message."""
        # Update last event time for watchdog
        self._last_event_ms = ticks_ms()
        
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
            self.event_handler.handle_event(message)

    def trigger_status_flash(self) -> None:
        """Trigger a single LED flash without overlapping tasks."""
        if self._flash_task is None or self._flash_task.done():
            self._flash_task = create_task(self.status_led.async_flash(1, 10))
    
    async def _start_web_server(self) -> None:
        """Start the web server for the configuration interface."""
        self.logger.info("Starting web configuration server on port 80...")
        await self.web_server.start(host='0.0.0.0', port=80)
