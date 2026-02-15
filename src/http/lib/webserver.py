"""
HA-Dash Web Server

This module provides the Microdot web server setup for hosting the HA-Dash
configuration interface and API endpoints.
"""
from http.lib.microdot import Microdot, send_file
from lib.ulogging import uLogger

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

class WebServer:
    """Web server for hosting the HA-Dash configuration interface."""
    
    def __init__(self, http_dir: str = "/http/") -> None:
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
    
    def _url_decode(self, text: str) -> str:
        """
        Decode URL-encoded text to prevent encoded traversal sequences.
        
        Args:
            text: URL-encoded text
            
        Returns:
            str: Decoded text
        """
        # Handle multiple rounds of encoding
        decoded = text
        for _ in range(3):  # Limit iterations to prevent infinite loops
            prev = decoded
            result = []
            i = 0
            while i < len(decoded):
                if decoded[i] == '%' and i + 2 < len(decoded):
                    try:
                        hex_chars = decoded[i+1:i+3]
                        char_code = int(hex_chars, 16)
                        result.append(chr(char_code))
                        i += 3
                    except (ValueError, OverflowError):
                        result.append(decoded[i])
                        i += 1
                else:
                    result.append(decoded[i])
                    i += 1
            decoded = ''.join(result)
            # Stop if no more changes (fully decoded)
            if decoded == prev:
                break
        return decoded
    
    def _normalize_path(self, path: str) -> str:
        """
        Normalize a path by resolving . and .. components.
        
        Args:
            path: The path to normalize
            
        Returns:
            str: Normalized path
        """
        # Split path into components
        parts = path.replace('\\', '/').split('/')
        normalized = []
        
        for part in parts:
            if part == '.' or part == '':
                # Skip current directory references and empty parts
                continue
            elif part == '..':
                # Move up one directory if possible
                if normalized:
                    normalized.pop()
            else:
                # Normal path component
                normalized.append(part)
        
        return '/'.join(normalized)
    
    def _is_safe_path(self, path: str) -> bool:
        """
        Validate that a path is safe and doesn't contain directory traversal sequences.
        Uses defense-in-depth approach with multiple validation layers.
        
        Args:
            path: The path to validate (from URL route parameter)
            
        Returns:
            bool: True if path is safe, False otherwise
        """
        # Reject empty paths
        if not path:
            return False
        
        # Reject paths with null bytes
        if '\x00' in path:
            return False
        
        # Reject absolute paths
        if path.startswith('/') or (len(path) > 1 and path[1] == ':'):
            return False
        
        # URL-decode the path to catch encoded traversal attempts
        decoded_path = self._url_decode(path)
        
        # Check decoded path for null bytes again
        if '\x00' in decoded_path:
            return False
        
        # Normalize the path to resolve . and .. components
        normalized = self._normalize_path(decoded_path)
        
        # After normalization, path should not be empty (would indicate traversal to root)
        if not normalized:
            return False
        
        # After normalization, path should not start with .. (would escape base directory)
        if normalized.startswith('..'):
            return False
        
        # Verify no .. components remain in the normalized path
        if '..' in normalized.split('/'):
            return False
        
        # Additional check: ensure path doesn't contain suspicious patterns
        suspicious_patterns = ['..\\', '/../', '\\..', '../']
        for pattern in suspicious_patterns:
            if pattern in path or pattern in decoded_path:
                return False
        
        return True
    
    def _register_static_routes(self) -> None:
        """Register routes for serving static files."""
        
        @self.app.route('/')
        async def index(request):
            """Serve the main index.html page."""
            return send_file(self.http_dir + 'index.html')
        
        @self.app.route('/favicon.ico')
        async def favicon(request):
            """Serve the favicon."""
            return send_file(self.http_dir + 'img/ha_logo.png', content_type='image/png')
        
        @self.app.route('/css/<path:path>')
        async def css(request, path):
            """Serve CSS files."""
            if not self._is_safe_path(path):
                return {'error': 'Invalid path'}, 400
            return send_file(self.http_dir + 'css/' + path)
        
        @self.app.route('/js/<path:path>')
        async def js(request, path):
            """Serve JavaScript files."""
            if not self._is_safe_path(path):
                return {'error': 'Invalid path'}, 400
            return send_file(self.http_dir + 'js/' + path)
        
        @self.app.route('/img/<path:path>')
        async def img(request, path):
            """Serve image files."""
            if not self._is_safe_path(path):
                return {'error': 'Invalid path'}, 400
            
            # Determine content type based on extension
            if path.endswith('.png'):
                content_type = 'image/png'
            elif path.endswith('.jpg') or path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif path.endswith('.gif'):
                content_type = 'image/gif'
            elif path.endswith('.svg'):
                content_type = 'image/svg+xml'
            else:
                content_type = 'application/octet-stream'
            
            return send_file(self.http_dir + 'img/' + path, content_type=content_type)
    
    def _register_error_handlers(self) -> None:
        """Register error handlers."""
        
        @self.app.errorhandler(404)
        async def not_found(request):
            """Handle 404 errors."""
            return {'error': 'Not found'}, 404
        
        @self.app.errorhandler(500)
        async def internal_error(request):
            """Handle 500 errors."""
            return {'error': 'Internal server error'}, 500
    
    def get_app(self) -> Microdot:
        """
        Get the Microdot app instance for registering additional routes.
        
        Returns:
            Microdot: The web server app instance
        """
        return self.app
    
    async def start(self, host: str | None = None, port: int | None = None) -> None:
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
