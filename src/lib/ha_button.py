from asyncio import Event, create_task
from lib.ulogging import uLogger
from lib.button import Button


class HAButton:
    """Home Assistant-aware button that toggles entities when pressed."""
    
    def __init__(self, component_id: str, pin: int, name: str, 
                 event_handler, ha_api) -> None:
        """
        Initialize an HA-aware button.
        
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
    
    def get_current_entity(self):
        """
        Get the entity this button controls on the current page.
        
        Returns:
            Entity ID string or None if not mapped on current page
        """
        current_page = self.event_handler.get_current_page()
        if current_page:
            return current_page.get_entity_for_button(self.component_id)
        return None
    
    async def handle_press(self) -> None:
        """Handle a button press by toggling the mapped entity."""
        entity_id = self.get_current_entity()
        
        if not entity_id:
            self.logger.warn(f"Button '{self.component_id}' not mapped to any entity on current page")
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
