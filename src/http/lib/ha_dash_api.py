"""
HA-Dash API Endpoints

This module defines the REST API endpoints for interacting with HA-Dash.
All API routes are registered with the web server and handle configuration,
status, and control operations.
"""
from lib.ulogging import uLogger


class HADashAPI:
    """API endpoints for HA-Dash configuration and control."""
    
    def __init__(self, web_server):
        """
        Initialize the API with a reference to the web server.
        
        Args:
            web_server: WebServer instance to register routes with
        """
        self.logger = uLogger("HADashAPI")
        self.web_server = web_server
        self.app = web_server.get_app()
        
        self.logger.info("HA-Dash API initialized")
    
    def register_routes(self):
        """Register all API routes with the web server."""
        self.logger.info("Registering API routes...")
        
        @self.app.route('/api/status')
        async def api_status(request):
            """Get the current HA-Dash status."""
            self.logger.info("API: Get status")
            return {
                'status': 'running',
                'version': '1.0.0'
            }
        
        @self.app.route('/api/config')
        async def api_get_config(request):
            """Get the current HA-Dash configuration."""
            self.logger.info("API: Get config")
            # TODO: Implement config retrieval
            return {
                'message': 'Configuration endpoint - coming soon'
            }
        
        @self.app.route('/api/config', methods=['POST'])
        async def api_update_config(request):
            """Update the HA-Dash configuration."""
            self.logger.info("API: Update config")
            # TODO: Implement config update
            return {
                'message': 'Configuration update endpoint - coming soon'
            }
        
        self.logger.info("API routes registered")
