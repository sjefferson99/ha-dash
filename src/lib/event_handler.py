from lib.ulogging import uLogger
from lib.dash_page import DashPage


class EventHandler:
    """Handles Home Assistant events and updates dashboard pages accordingly."""
    
    def __init__(self, ha_api) -> None:
        """
        Initialize the event handler.
        
        Args:
            ha_api: HomeAssistantAPI instance for state queries
        """
        self.logger = uLogger("EventHandler")
        self.ha_api = ha_api
        self.pages = {}  # {page_name: DashPage}
        self.current_page = None
        self.logger.info("EventHandler initialized")
    
    def register_page(self, page: DashPage) -> None:
        """
        Register a dashboard page.
        
        Args:
            page: DashPage instance to register
        """
        self.pages[page.name] = page
        self.logger.info(f"Registered page: {page.name}")
        
        # Set as current page if it's the first one
        if self.current_page is None:
            self.set_current_page(page.name)
    
    def set_current_page(self, page_name: str) -> bool:
        """
        Switch to a different page.
        
        Args:
            page_name: Name of the page to switch to
            
        Returns:
            True if successful, False if page doesn't exist
        """
        if page_name in self.pages:
            self.current_page = page_name
            self.logger.info(f"Switched to page: {page_name}")
            
            # Sync physical LEDs to match virtual state (no API calls needed!)
            new_page = self.pages[page_name]
            new_page.sync_physical_to_virtual()
            
            return True
        else:
            self.logger.error(f"Page '{page_name}' not found")
            return False
    
    def get_current_page(self) -> DashPage | None:
        """
        Get the currently active page.
        
        Returns:
            The current DashPage instance, or None if no page is active
        """
        if self.current_page:
            return self.pages.get(self.current_page)
        return None
    
    def handle_event(self, event_message: dict) -> None:
        """
        Process a Home Assistant event and update dashboard if needed.
        
        Args:
            event_message: The complete event message from Home Assistant WebSocket
        """
        # Check if this is a state_changed event
        if event_message.get("type") != "event":
            return
        
        event = event_message.get("event", {})
        if event.get("event_type") != "state_changed":
            return
        
        # Extract state change data
        data = event.get("data", {})
        entity_id = data.get("entity_id")
        new_state = data.get("new_state", {})
        
        if not entity_id:
            return
        
        # Get the state value
        state_value = None
        if isinstance(new_state, dict):
            state_value = new_state.get("state")
        
        if state_value is None:
            return
        
        # Update virtual state on ALL pages that have this entity registered
        # This ensures page switches don't require API resync calls
        current_page = self.get_current_page()
        pages_updated = []
        
        for page_name, page in self.pages.items():
            if page.is_entity_registered(entity_id):
                # Update virtual state on all pages, but only update physical GPIO on current page
                is_current = (page == current_page)
                updated = page.update_led_state(entity_id, state_value, update_physical=is_current)
                
                if updated:
                    pages_updated.append(page_name)
        
        # Log summary of updates
        if pages_updated:
            self.logger.info(f"Updated {entity_id}: {state_value} on pages: {', '.join(pages_updated)}")
    
    async def resync_current_page(self) -> None:
        """Resynchronize the current page with Home Assistant states."""
        current_page = self.get_current_page()
        if current_page:
            self.logger.info(f"Resyncing current page: {current_page.name}")
            await current_page.resync(self.ha_api)
        else:
            self.logger.warn("No current page to resync")
    
    async def resync_all_pages(self) -> None:
        """
        Resynchronize all pages with current Home Assistant states.
        This should be called on startup to ensure all pages have initial states.
        """
        self.logger.info(f"Resyncing all {len(self.pages)} pages with Home Assistant")
        
        for page_name, page in self.pages.items():
            try:
                await page.resync(self.ha_api)
            except Exception as e:
                self.logger.error(f"Failed to resync page '{page_name}': {e}")
        
        self.logger.info("All pages resync complete")
    
    def get_registered_entities(self) -> dict:
        """
        Get all registered entities across all pages.
        
        Returns:
            Dictionary mapping page names to lists of entity IDs
        """
        entities_by_page = {}
        for page_name, page in self.pages.items():
            entities_by_page[page_name] = page.get_registered_entities()
        return entities_by_page
