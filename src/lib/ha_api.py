from lib.ulogging import uLogger
import lib.uaiohttpclient as httpclient
from lib.networking import WirelessNetwork
from config import HA_HOST, HA_PORT, HA_TOKEN
from json import loads, dumps
import gc


class HomeAssistantAPI:
    """
    API wrapper for Home Assistant REST API.
    Provides methods to interact with HA entities and services.
    """
    def __init__(self, network: WirelessNetwork) -> None:
        """Initialize the REST API client with network and auth settings."""
        self.log = uLogger("HA-API")
        self.wifi = network
        # Store both HTTP and HTTPS variants using the same port
        # Try HTTP first (faster), fall back to HTTPS on the same port if needed
        self.http_base_url = f"http://{HA_HOST}:{HA_PORT}/api/"
        self.https_base_url = f"https://{HA_HOST}:{HA_PORT}/api/"
        self.base_url = self.http_base_url  # Try HTTP first (faster)
        self.token = HA_TOKEN
        self.protocol_confirmed = False  # Track if we've confirmed which protocol works
    
    async def get_state(self, entity_id: str) -> dict:
        """
        Get the current state of a Home Assistant entity.
        
        Args:
            entity_id: The entity ID (e.g., 'light.living_room')
        
        Returns:
            dict containing entity state information
        """
        url = f"{self.base_url}states/{entity_id}"
        return await self._make_request("GET", url)
    
    async def set_state(self, entity_id: str, state: str, attributes: dict | None = None) -> dict:
        """
        Set the state of a Home Assistant entity.
        Note: This updates the state in HA's state machine but doesn't trigger device actions.
        For controlling devices, use call_service() instead.
        
        Args:
            entity_id: The entity ID
            state: The new state value (e.g., 'on', 'off')
            attributes: Optional dict of attributes
        
        Returns:
            dict containing the updated state
        """
        url = f"{self.base_url}states/{entity_id}"
        json_data = dumps({"state": state, "attributes": attributes or {}})
        return await self._make_request("POST", url, json_data)
    
    async def call_service(self, domain: str, service: str, entity_id: str | None = None, **kwargs) -> dict:
        """
        Call a Home Assistant service.
        
        Args:
            domain: Service domain (e.g., 'light', 'switch', 'homeassistant')
            service: Service name (e.g., 'turn_on', 'turn_off', 'toggle')
            entity_id: Optional entity ID to target
            **kwargs: Additional service data
        
        Returns:
            dict containing the service call result
        """
        url = f"{self.base_url}services/{domain}/{service}"
        service_data = kwargs.copy()
        if entity_id:
            service_data["entity_id"] = entity_id
        json_data = dumps(service_data)
        return await self._make_request("POST", url, json_data)
    
    async def toggle_light(self, entity_id: str) -> dict:
        """
        Toggle a light entity.
        
        Args:
            entity_id: The light entity ID (e.g., 'light.living_room')
        
        Returns:
            dict containing the service call result
        """
        return await self.call_service("light", "toggle", entity_id)
    
    async def turn_on_light(self, entity_id: str, **kwargs) -> dict:
        """
        Turn on a light entity.
        
        Args:
            entity_id: The light entity ID
            **kwargs: Optional parameters (brightness, color, etc.)
        
        Returns:
            dict containing the service call result
        """
        return await self.call_service("light", "turn_on", entity_id, **kwargs)
    
    async def turn_off_light(self, entity_id: str) -> dict:
        """
        Turn off a light entity.
        
        Args:
            entity_id: The light entity ID
        
        Returns:
            dict containing the service call result
        """
        return await self.call_service("light", "turn_off", entity_id)
    
    async def _make_request(self, method: str, url: str, json_data: str = "") -> dict:
        """
        Internal method for making an API request to Home Assistant.
        Tries HTTP first for speed, falls back to HTTPS if needed.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            json_data: Optional JSON data string for POST requests
        
        Returns:
            dict containing the response data
        
        Raises:
            ValueError: If the HTTP status code indicates an error
        """
        gc.collect()
        
        self.log.info(f"Calling HA API: {url}, method: {method}")
        
        # If protocol not yet confirmed, try HTTP first, then HTTPS
        urls_to_try = [url] if self.protocol_confirmed else [
            url.replace(self.base_url, self.http_base_url, 1),
            url.replace(self.base_url, self.https_base_url, 1)
        ]
        
        last_error = None
        for attempt_url in urls_to_try:
            try:
                await self.wifi.check_network_access()
                
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(json_data))
                }
                
                request = await httpclient.request(method, attempt_url, headers=headers, json_data=json_data)
                status = getattr(request, "status", None)
                self.log.info(f"Request status: {status}")
                
                response = await request.read()
                self.log.info(f"Response data: {response}")
                
                data = {}
                if response:
                    data = loads(response)
                    self.log.info(f"Parsed JSON: {data}")
                
                if status is not None and 200 <= status < 300:
                    # Success! Confirm this protocol for future requests
                    if not self.protocol_confirmed:
                        self.base_url = attempt_url.split('/api/')[0] + '/api/'
                        self.protocol_confirmed = True
                        self.log.info(f"Protocol confirmed: {self.base_url}")
                    self.log.info("HA API request successful")
                    return data
                else:
                    raise ValueError(f"HA API error: Status {status}, Response: {response}")
                    
            except Exception as e:
                self.log.warn(f"Failed to call HA API: {attempt_url}. Exception: {e}")
                last_error = e
                continue
        
        # If we get here, all attempts failed
        self.log.error("Failed to call HA API with all protocol attempts")
        raise last_error if last_error else ValueError("Failed to connect to HA API")
        
        gc.collect()
