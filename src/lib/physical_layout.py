from lib.ulogging import uLogger
from machine import Pin


class PhysicalComponent:
    """Represents a physical hardware component (LED or button)."""
    
    def __init__(self, component_id: str, component_type: str, pin_number: int, name: str) -> None:
        """
        Initialize a physical component.
        
        Args:
            component_id: Unique identifier for this component
            component_type: Type of component ("led" or "button")
            pin_number: GPIO pin number
            name: Human-readable name
        """
        self.id = component_id
        self.type = component_type
        self.pin = pin_number
        self.name = name
        self.pin_obj = None
        self.state = False  # For LEDs
        
        # Initialize the GPIO pin based on type
        if component_type == "led":
            self.pin_obj = Pin(pin_number, Pin.OUT)
            self.pin_obj.value(0)  # Start with LED off
        elif component_type == "button":
            # Buttons are managed by the Button class elsewhere
            pass


class PhysicalLayout:
    """Manages the physical hardware layout - the database of actual components."""
    
    def __init__(self) -> None:
        """Initialize the physical layout manager."""
        self.logger = uLogger("PhysicalLayout")
        self.components = {}  # {component_id: PhysicalComponent}
        self.logger.info("PhysicalLayout initialized")
    
    def register_component(self, component_id: str, component_type: str, 
                          pin_number: int, name: str) -> None:
        """
        Register a physical hardware component.
        
        Args:
            component_id: Unique identifier for this component
            component_type: Type of component ("led" or "button")
            pin_number: GPIO pin number
            name: Human-readable name
        """
        if component_id in self.components:
            self.logger.warn(f"Component '{component_id}' already registered, replacing")
        
        component = PhysicalComponent(component_id, component_type, pin_number, name)
        self.components[component_id] = component
        
        self.logger.info(f"Registered {component_type} '{component_id}' ({name}) on pin {pin_number}")
    
    def get_component(self, component_id: str) -> PhysicalComponent | None:
        """
        Get a physical component by ID.
        
        Args:
            component_id: The unique identifier of the component
            
        Returns:
            PhysicalComponent instance or None if not found
        """
        return self.components.get(component_id)
    
    def get_led(self, component_id: str) -> PhysicalComponent | None:
        """
        Get an LED component by ID.
        
        Args:
            component_id: The unique identifier of the LED
            
        Returns:
            PhysicalComponent instance or None if not found or not an LED
        """
        component = self.components.get(component_id)
        if component and component.type == "led":
            return component
        return None
    
    def get_button(self, component_id: str) -> PhysicalComponent | None:
        """
        Get a button component by ID.
        
        Args:
            component_id: The unique identifier of the button
            
        Returns:
            PhysicalComponent instance or None if not found or not a button
        """
        component = self.components.get(component_id)
        if component and component.type == "button":
            return component
        return None
    
    def set_led_state(self, component_id: str, state: bool) -> bool:
        """
        Set the physical state of an LED.
        
        Args:
            component_id: The unique identifier of the LED
            state: True for on, False for off
            
        Returns:
            True if successful, False if component not found or not an LED
        """
        led = self.get_led(component_id)
        if led is None:
            return False
        
        led.state = state
        if led.pin_obj:
            led.pin_obj.value(1 if state else 0)
        
        return True
    
    def get_led_state(self, component_id: str) -> bool:
        """
        Get the current state of an LED.
        
        Args:
            component_id: The unique identifier of the LED
            
        Returns:
            True if on, False if off or not found
        """
        led = self.get_led(component_id)
        if led:
            return led.state
        return False
    
    def get_all_leds(self) -> list:
        """
        Get all LED components.
        
        Returns:
            List of PhysicalComponent instances that are LEDs
        """
        return [c for c in self.components.values() if c.type == "led"]
    
    def get_all_buttons(self) -> list:
        """
        Get all button components.
        
        Returns:
            List of PhysicalComponent instances that are buttons
        """
        return [c for c in self.components.values() if c.type == "button"]
    
    def component_exists(self, component_id: str) -> bool:
        """
        Check if a component exists.
        
        Args:
            component_id: The unique identifier to check
            
        Returns:
            True if component exists, False otherwise
        """
        return component_id in self.components
