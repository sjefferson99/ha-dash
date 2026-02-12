from lib.ulogging import uLogger


class DashPage:
    """Represents a virtual dashboard page that maps entities to physical components."""
    
    def __init__(self, name: str, description: str, physical_layout) -> None:
        """
        Initialize a dashboard page.
        
        Args:
            name: The name of the page (e.g., "office")
            description: A description of what this page displays
            physical_layout: PhysicalLayout instance containing hardware database
        """
        self.name = name
        self.description = description
        self.physical_layout = physical_layout
        self.logger = uLogger(f"DashPage:{name}")
        
        # Entity to component mappings
        self._entity_to_led = {}     # {entity_id: component_id}
        self._entity_to_button = {}  # {entity_id: component_id}
        
        # Virtual state for entities (independent of physical state)
        self._entity_states = {}  # {entity_id: state_value}
        
        self.logger.info(f"Page '{name}' initialized: {description}")
    
    def register_led(self, component_id: str, entity_id: str) -> None:
        """
        Map an entity to an LED component.
        
        Args:
            component_id: Physical component ID from the layout database
            entity_id: Home Assistant entity ID to track
        """
        # Verify the component exists and is an LED
        if not self.physical_layout.get_led(component_id):
            self.logger.error(f"LED component '{component_id}' not found in physical layout")
            return
        
        self._entity_to_led[entity_id] = component_id
        self.logger.info(f"Mapped entity '{entity_id}' to LED '{component_id}'")
    
    def register_button(self, component_id: str, entity_id: str) -> None:
        """
        Map an entity to a button component.
        
        Args:
            component_id: Physical component ID from the layout database
            entity_id: Home Assistant entity ID to control
        """
        # Verify the component exists and is a button
        if not self.physical_layout.get_button(component_id):
            self.logger.error(f"Button component '{component_id}' not found in physical layout")
            return
        
        self._entity_to_button[entity_id] = component_id
        self.logger.info(f"Mapped entity '{entity_id}' to button '{component_id}'")
    
    def update_led_state(self, entity_id: str, state: str, update_physical: bool = True) -> bool:
        """
        Update the LED state based on entity state.
        
        Args:
            entity_id: The Home Assistant entity ID
            state: The new state (e.g., "on", "off")
            update_physical: If True, update physical GPIO pin; if False, only update virtual state
            
        Returns:
            True if the state was changed, False if entity not registered or no change
        """
        component_id = self._entity_to_led.get(entity_id)
        if component_id is None:
            return False
        
        # Store virtual state
        new_state = (state.lower() == "on")
        old_state = self._entity_states.get(entity_id)
        
        if old_state != new_state:
            self._entity_states[entity_id] = new_state
            
            if update_physical:
                # Update physical LED through the layout manager
                self.physical_layout.set_led_state(component_id, new_state)
                self.logger.info(f"Updated LED '{component_id}' for {entity_id}: {state} (physical)")
            else:
                self.logger.info(f"Updated virtual state for {entity_id}: {state} (virtual only)")
            
            return True
        
        return False
    
    def sync_physical_to_virtual(self) -> None:
        """
        Sync all physical LEDs to match their virtual state.
        Called when switching to this page to ensure physical matches virtual.
        """
        synced_count = 0
        for entity_id, component_id in self._entity_to_led.items():
            virtual_state = self._entity_states.get(entity_id, False)
            self.physical_layout.set_led_state(component_id, virtual_state)
            synced_count += 1
        
        self.logger.info(f"Synced {synced_count} physical LEDs to virtual state")
    
    def is_entity_registered(self, entity_id: str) -> bool:
        """
        Check if an entity is registered on this page.
        
        Args:
            entity_id: The Home Assistant entity ID to check
            
        Returns:
            True if the entity is registered for either LED or button
        """
        return entity_id in self._entity_to_led or entity_id in self._entity_to_button
    
    def get_registered_entities(self) -> list:
        """
        Get a list of all entities registered on this page.
        
        Returns:
            List of entity IDs registered on this page
        """
        entities = set()
        entities.update(self._entity_to_led.keys())
        entities.update(self._entity_to_button.keys())
        return list(entities)
    
    def get_entity_for_button(self, component_id: str):
        """
        Get the entity mapped to a button component.
        
        Args:
            component_id: The physical component ID
            
        Returns:
            The entity ID mapped to this button, or None if not found
        """
        # Reverse lookup: find entity_id where value is component_id
        for entity_id, cid in self._entity_to_button.items():
            if cid == component_id:
                return entity_id
        return None
