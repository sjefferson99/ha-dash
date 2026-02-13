import json
from lib.ulogging import uLogger
from lib.dash_page import DashPage
from lib.physical_layout import PhysicalLayout


class DashboardConfig:
    """Manages dashboard configuration from JSON file."""
    
    def __init__(self, config_file: str = "dashboard_config.json") -> None:
        """
        Initialize the configuration manager.
        
        Args:
            config_file: Path to the JSON configuration file
        """
        self.config_file = config_file
        self.logger = uLogger("DashboardConfig")
        self.config = None
        self.logger.info(f"DashboardConfig initialized with file: {config_file}")
    
    def load(self) -> dict:
        """
        Load configuration from JSON file.
        
        Returns:
            The configuration dictionary
            
        Raises:
            Exception if file cannot be read or parsed
        """
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
            self.logger.info(f"Loaded configuration from {self.config_file}")
            return self.config
        except OSError as e:
            self.logger.error(f"Failed to read config file: {e}")
            raise
        except ValueError as e:
            self.logger.error(f"Failed to parse JSON config: {e}")
            raise
    
    def save(self, config = None) -> None:
        """
        Save configuration to JSON file.
        
        Args:
            config: Configuration dictionary to save. If None, saves current config.
            
        Raises:
            Exception if file cannot be written
        """
        if config is not None:
            self.config = config
        
        if self.config is None:
            self.logger.error("No configuration to save")
            raise ValueError("No configuration loaded")
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f)
            self.logger.info(f"Saved configuration to {self.config_file}")
        except OSError as e:
            self.logger.error(f"Failed to write config file: {e}")
            raise
    
    def create_physical_layout(self):
        """
        Create PhysicalLayout instance from the loaded configuration.
        
        Returns:
            PhysicalLayout instance with all components registered
            
        Raises:
            ValueError if configuration not loaded
        """
        if self.config is None:
            raise ValueError("Configuration not loaded. Call load() first.")
        
        layout = PhysicalLayout()
        physical_config = self.config.get("physical_layout", {})
        
        # Register LEDs
        for led_config in physical_config.get("leds", []):
            component_id = led_config.get("id")
            name = led_config.get("name", component_id)
            pin = led_config.get("pin")
            
            if component_id and pin is not None:
                layout.register_component(component_id, "led", pin, name)
            else:
                self.logger.warn(f"Invalid LED config: {led_config}")
        
        # Register buttons
        for button_config in physical_config.get("buttons", []):
            component_id = button_config.get("id")
            name = button_config.get("name", component_id)
            pin = button_config.get("pin")
            
            if component_id and pin is not None:
                layout.register_component(component_id, "button", pin, name)
            else:
                self.logger.warn(f"Invalid button config: {button_config}")
        
        self.logger.info(f"Created physical layout with {len(layout.components)} components")
        return layout
    
    def create_pages(self, physical_layout, ha_buttons: dict) -> list:
        """
        Create DashPage objects from the loaded configuration.
        
        Args:
            physical_layout: PhysicalLayout instance to use for component lookups
            ha_buttons: Dictionary of HAButton instances {component_id: HAButton}
        
        Returns:
            List of DashPage objects
            
        Raises:
            ValueError if configuration not loaded
        """
        if self.config is None:
            raise ValueError("Configuration not loaded. Call load() first.")
        
        pages = []
        page_configs = self.config.get("pages", [])
        
        for page_config in page_configs:
            name = page_config.get("name")
            description = page_config.get("description", "")
            
            if not name:
                self.logger.warn("Page configuration missing name, skipping")
                continue
            
            # Create the page with physical layout reference
            page = DashPage(name, description, physical_layout)
            
            # Register component mappings
            for mapping in page_config.get("mappings", []):
                component_id = mapping.get("component_id")
                
                if not component_id:
                    self.logger.warn(f"Mapping missing component_id on page '{name}': {mapping}")
                    continue
                
                # Determine if this is an LED or button mapping
                component = physical_layout.get_component(component_id)
                if component is None:
                    self.logger.warn(f"Component '{component_id}' not found in physical layout")
                    continue
                
                if component.type == "led":
                    entity_id = mapping.get("entity_id")
                    if not entity_id:
                        self.logger.warn(f"LED mapping missing entity_id on page '{name}': {mapping}")
                        continue
                    page.register_led(component_id, entity_id)
                    
                elif component.type == "button":
                    # Get the HAButton instance for this component
                    ha_button = ha_buttons.get(component_id)
                    if not ha_button:
                        self.logger.warn(f"HAButton '{component_id}' not found for page '{name}'")
                        continue
                    
                    # Build action configuration for this button on this page
                    action = mapping.get("action", "toggle_entity")  # Default to toggle_entity for backward compatibility
                    
                    action_config = {"action": action}
                    
                    if action == "toggle_entity":
                        entity_id = mapping.get("entity_id")
                        if not entity_id:
                            self.logger.warn(f"Button toggle_entity action missing entity_id on page '{name}': {mapping}")
                            continue
                        action_config["entity_id"] = entity_id
                    elif action == "next_dashboard":
                        # No additional config needed
                        pass
                    else:
                        self.logger.warn(f"Unknown action '{action}' for button '{component_id}' on page '{name}'")
                        continue
                    
                    # Register the HAButton with the page (page stores the action config)
                    page.register_button(ha_button, action_config)
                    
                else:
                    self.logger.warn(f"Unknown component type '{component.type}' for '{component_id}'")
            
            pages.append(page)
            self.logger.info(f"Created page '{name}' with {len(page_config.get('mappings', []))} mappings")
        
        return pages
    
    def get_default_page(self):
        """
        Get the default page name from configuration.
        
        Returns:
            The default page name, or None if not specified
        """
        if self.config is None:
            return None
        return self.config.get("default_page")
    
    def update_page(self, page_name: str, page_config: dict) -> None:
        """
        Update or add a page configuration.
        
        Args:
            page_name: Name of the page to update
            page_config: New page configuration dictionary
        """
        if self.config is None:
            raise ValueError("Configuration not loaded. Call load() first.")
        
        pages = self.config.get("pages", [])
        
        # Find existing page or add new one
        for i, page in enumerate(pages):
            if page.get("name") == page_name:
                pages[i] = page_config
                self.logger.info(f"Updated page configuration: {page_name}")
                return
        
        # Page not found, add it
        pages.append(page_config)
        self.config["pages"] = pages
        self.logger.info(f"Added new page configuration: {page_name}")
    
    def remove_page(self, page_name: str) -> bool:
        """
        Remove a page configuration.
        
        Args:
            page_name: Name of the page to remove
            
        Returns:
            True if page was removed, False if not found
        """
        if self.config is None:
            raise ValueError("Configuration not loaded. Call load() first.")
        
        pages = self.config.get("pages", [])
        original_count = len(pages)
        
        pages = [p for p in pages if p.get("name") != page_name]
        self.config["pages"] = pages
        
        if len(pages) < original_count:
            self.logger.info(f"Removed page configuration: {page_name}")
            return True
        else:
            self.logger.warn(f"Page not found: {page_name}")
            return False
    
    def set_default_page(self, page_name: str) -> None:
        """
        Set the default page.
        
        Args:
            page_name: Name of the page to set as default
        """
        if self.config is None:
            raise ValueError("Configuration not loaded. Call load() first.")
        
        self.config["default_page"] = page_name
        self.logger.info(f"Set default page to: {page_name}")
