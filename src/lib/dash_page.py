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
        
        # Button configurations
        self._button_actions = {}  # {component_id: {"ha_button": HAButton, "action": {...}}}
        
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
    
    def register_button(self, ha_button, action_config: dict) -> None:
        """
        Register a button on this page with its action configuration.
        
        Args:
            ha_button: HAButton instance to register
            action_config: Action configuration dictionary
                          e.g., {"action": "toggle_entity", "entity_id": "light.living_room"}
                          or {"action": "next_dashboard"}
        """
        # Verify the component exists and is a button in physical layout
        if not self.physical_layout.get_button(ha_button.component_id):
            self.logger.error(f"Button component '{ha_button.component_id}' not found in physical layout")
            return
        
        action_type = action_config.get("action")
        if not action_type:
            self.logger.error("Button action configuration missing 'action' field")
            return
        
        # Store both the HAButton reference and the action config
        self._button_actions[ha_button.component_id] = {
            "ha_button": ha_button,
            "action": action_config
        }
        
        if action_type == "toggle_entity":
            entity_id = action_config.get("entity_id")
            self.logger.info(f"Registered button '{ha_button.component_id}' to toggle entity '{entity_id}'")
        elif action_type == "next_dashboard":
            self.logger.info(f"Registered button '{ha_button.component_id}' for next_dashboard action")
        else:
            self.logger.warn(f"Unknown action type '{action_type}' for button '{ha_button.component_id}'")
    
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
        new_state = (str(state).lower() == "on")
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
        # Check LEDs
        if entity_id in self._entity_to_led:
            return True
        
        # Check button actions
        for button_config in self._button_actions.values():
            action = button_config.get("action", {})
            if action.get("entity_id") == entity_id:
                return True
        
        return False
    
    def get_registered_entities(self) -> list:
        """
        Get a list of all entities registered on this page.
        
        Returns:
            List of entity IDs registered on this page
        """
        entities = set()
        entities.update(self._entity_to_led.keys())
        
        # Add entities from button actions on this page
        for button_config in self._button_actions.values():
            action = button_config.get("action", {})
            entity_id = action.get("entity_id")
            if entity_id:
                entities.add(entity_id)
        
        return list(entities)
    
    def get_action_for_button(self, component_id: str) -> dict | None:
        """
        Get the action configuration for a button on this page.
        
        Args:
            component_id: The physical component ID of the button
            
        Returns:
            Action configuration dict or None if button not on this page
        """
        button_config = self._button_actions.get(component_id)
        if button_config:
            return button_config.get("action")
        return None
    
    async def resync(self, ha_api, update_physical: bool = True) -> None:
        """
        Resynchronize all entities on this page with current Home Assistant states.
        Fetches the current state of each registered entity and updates the LED states.
        
        Args:
            ha_api: HomeAssistantAPI instance for fetching states
            update_physical: If True, update physical LEDs; if False, only update virtual state
        """
        mode = "physical+virtual" if update_physical else "virtual only"
        self.logger.info(f"Resyncing page '{self.name}' with Home Assistant ({mode})")
        synced_count = 0
        failed_count = 0
        
        # Get all registered LED entities
        for entity_id in self._entity_to_led.keys():
            try:
                # Fetch current state from Home Assistant
                state_data = await ha_api.get_state(entity_id)
                
                if state_data and isinstance(state_data, dict):
                    state_value = state_data.get("state")
                    
                    if state_value is not None:
                        # Update virtual state (and optionally physical)
                        self.update_led_state(entity_id, state_value, update_physical=update_physical)
                        synced_count += 1
                    else:
                        self.logger.warn(f"No state value in response for {entity_id}")
                        failed_count += 1
                else:
                    self.logger.warn(f"Invalid state data for {entity_id}")
                    failed_count += 1
                    
            except Exception as e:
                self.logger.error(f"Failed to fetch state for {entity_id}: {e}")
                failed_count += 1
        
        self.logger.info(f"Resync complete: {synced_count} updated, {failed_count} failed")
