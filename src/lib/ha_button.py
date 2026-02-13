from asyncio import Event, create_task
from lib.ulogging import uLogger
from lib.button import Button


class HAButton:
    """Physical button that can execute various Home Assistant actions."""
    
    def __init__(self, component_id: str, pin: int, name: str, 
                 event_handler, ha_api) -> None:
        """
        Initialize a physical button.
        
        Args:
            component_id: Unique component ID from physical layout
            pin: GPIO pin number
            name: Human-readable name
            event_handler: EventHandler instance to get current page
            ha_api: HomeAssistantAPI instance for entity control
        """
        self.component_id = component_id
        self.name = name
        self.event_handler = event_handler
        self.ha_api = ha_api
        self.logger = uLogger(f"HAButton:{component_id}")
        
        # Create event and underlying Button instance
        self.button_event = Event()
        self.button = Button(pin, name, self.button_event)
        
        self.logger.info(f"HAButton '{component_id}' initialized on pin {pin}")
    
    def get_button_action(self):
        """
        Get the action configuration for this button on the current page.
        
        Returns:
            Dictionary with action config or None if not mapped on current page
            Format: {"action": "toggle_entity", "entity_id": "light.living_room"}
                 or {"action": "next_dashboard"}
        """
        current_page = self.event_handler.get_current_page()
        if current_page:
            return current_page.get_action_for_button(self.component_id)
        return None
    
    async def handle_press(self) -> None:
        """Handle a button press by executing the configured action."""
        action_config = self.get_button_action()
        
        if not action_config:
            self.logger.warn(f"Button '{self.component_id}' not mapped on current page")
            return
        
        action_type = action_config.get("action")
        
        if action_type == "toggle_entity":
            await self._handle_toggle_entity(action_config)
        elif action_type == "next_dashboard":
            await self._handle_next_dashboard()
        else:
            self.logger.error(f"Unknown action type: {action_type}")
    
    async def _handle_toggle_entity(self, action_config: dict) -> None:
        """Handle toggling a Home Assistant entity."""
        entity_id = action_config.get("entity_id")
        
        if not entity_id:
            self.logger.error("toggle_entity action missing entity_id")
            return
        
        self.logger.info(f"Button '{self.component_id}' pressed, toggling {entity_id}")
        
        try:
            # Toggle the entity - service calls return array of states after action
            result = await self.ha_api.toggle_light(entity_id)
            self.logger.info(f"Entity {entity_id} toggled successfully")
            
            # Log the new state if available
            if isinstance(result, list) and len(result) > 0:
                current_state = result[0].get('state', 'toggled')
                self.logger.info(f"Entity is now: {current_state}")
            else:
                self.logger.info("Entity toggled (state not returned)")
            
        except Exception as e:
            self.logger.error(f"Failed to toggle entity {entity_id}: {e}")
    
    async def _handle_next_dashboard(self) -> None:
        """Handle switching to the next dashboard page."""
        self.logger.info(f"Button '{self.component_id}' pressed, switching to next dashboard")
        
        # Get all registered pages
        pages = list(self.event_handler.pages.keys())
        
        if len(pages) == 0:
            self.logger.warn("No pages available")
            return
        
        # Find current page index
        current_page_name = self.event_handler.current_page
        
        if current_page_name not in pages:
            # No current page or invalid, go to first
            next_page_name = pages[0]
        else:
            # Get next page (wrap around to first if at end)
            current_index = pages.index(current_page_name)
            next_index = (current_index + 1) % len(pages)
            next_page_name = pages[next_index]
        
        self.logger.info(f"Switching from '{current_page_name}' to '{next_page_name}'")
        self.event_handler.set_current_page(next_page_name)
    
    async def monitor(self) -> None:
        """Monitor button events and dispatch actions."""
        self.logger.info(f"Starting monitor for button '{self.component_id}'")
        
        while True:
            # Wait for button event to be set
            await self.button_event.wait()
            
            # Handle the press
            await self.handle_press()
            
            # Clear the event for next press
            self.button_event.clear()
    
    def start_tasks(self) -> None:
        """Start background tasks for this button."""
        create_task(self.button.wait_for_press())
        create_task(self.monitor())
        self.logger.info(f"Started tasks for button '{self.component_id}'")
