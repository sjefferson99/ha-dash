"""
HA-Dash Web Server

This module provides the Microdot web server setup for hosting the HA-Dash
configuration interface and API endpoints.
"""
import sys
sys.path.insert(0, '/http/lib')
from microdot.microdot import Microdot, send_file
from lib.ulogging import uLogger


class WebServer:
    """Web server for hosting the HA-Dash configuration interface."""
    
    def __init__(self, http_dir="/http/"):
        """
        Initialize the web server.
        
        Args:
            http_dir: Base directory for static files (default: /http/)
        """
        self.logger = uLogger("WebServer")
        self.http_dir = http_dir
        self.app = Microdot()
        self.host = '0.0.0.0'
        self.port = 80
        
        # Register static file routes and error handlers
        self._register_static_routes()
        self._register_error_handlers()
        
        self.logger.info("Web server initialized")
    
    def _register_static_routes(self):
        """Register routes for serving static files."""
        
        @self.app.route('/')
        async def index(request):
            """Serve the main index.html page."""
            self.logger.info("Serving index.html")
            return send_file(self.http_dir + 'index.html')
        
        @self.app.route('/css/<path:path>')
        async def css(request, path):
            """Serve CSS files."""
            self.logger.info(f"Serving CSS: {path}")
            return send_file(self.http_dir + 'css/' + path)
        
        @self.app.route('/js/<path:path>')
        async def js(request, path):
            """Serve JavaScript files."""
            self.logger.info(f"Serving JS: {path}")
            return send_file(self.http_dir + 'js/' + path)
    
    def _register_error_handlers(self):
        """Register error handlers."""
        
        @self.app.errorhandler(404)
        async def not_found(request):
            """Handle 404 errors."""
            return {'error': 'Not found'}, 404
        
        @self.app.errorhandler(500)
        async def internal_error(request):
            """Handle 500 errors."""
            return {'error': 'Internal server error'}, 500
    
    def get_app(self):
        """
        Get the Microdot app instance for registering additional routes.
        
        Returns:
            Microdot: The web server app instance
        """
        return self.app
    
    async def start(self, host=None, port=None):
        """
        Start the web server.
        
        Args:
            host: Host address to bind to (default: 0.0.0.0)
            port: Port to listen on (default: 80)
        """
        if host:
            self.host = host
        if port:
            self.port = port
            
        self.logger.info(f"Starting web server on {self.host}:{self.port}")
        try:
            await self.app.start_server(host=self.host, port=self.port)
        except Exception as e:
            self.logger.error(f"Failed to start web server: {e}")
            raise
