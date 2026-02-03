from lib.ulogging import uLogger
from lib.networking import WirelessNetwork
from config import HA_HOST, HA_PORT, HA_TOKEN
from json import loads, dumps
from os import urandom
from ubinascii import b2a_base64
from utime import ticks_ms, ticks_diff
import asyncio
try:
    import ssl
except ImportError:
    ssl = None


class HomeAssistantWebSocket:
    """
    Async WebSocket client for Home Assistant's /api/websocket endpoint.
    Includes keepalive ping/pong and auto-reconnect with backoff.

    Note: Fragmented frames (FIN=0) are not supported; frames are assumed
    to be complete in a single message.

    TLS note: certificate verification is disabled (CERT_NONE) for simplicity
    and performance on microcontrollers. This is insecure on untrusted networks.
    """
    def __init__(
        self,
        network: WirelessNetwork,
        *,
        ping_interval_s: int = 30,
        pong_timeout_s: int = 10,
        reconnect_initial_delay_s: int = 1,
        reconnect_max_delay_s: int = 30
    ) -> None:
        """Initialize the WebSocket client and keepalive settings."""
        self.log = uLogger("HA-WS")
        self.wifi = network
        self.host = HA_HOST
        self.port = int(HA_PORT)
        self.token = HA_TOKEN
        self.reader = None
        self.writer = None
        self.connected = False
        self.use_ssl = False
        self._message_id = 1
        self.ping_interval_s = ping_interval_s
        self.pong_timeout_s = pong_timeout_s
        self.reconnect_initial_delay_s = reconnect_initial_delay_s
        self.reconnect_max_delay_s = reconnect_max_delay_s
        self._last_pong_ms = ticks_ms()

    def is_open(self) -> bool:
        """Return True when the socket is connected and usable."""
        return self.connected and self.writer is not None

    async def connect(self) -> None:
        """Connect to Home Assistant via WS or WSS with fallback."""
        await self.wifi.check_network_access()
        last_error = None
        for use_ssl in (False, True):
            try:
                await self._open_connection(use_ssl)
                self.use_ssl = use_ssl
                self.connected = True
                self._last_pong_ms = ticks_ms()
                self.log.info("WebSocket connected")
                return
            except Exception as e:
                last_error = e
                self.log.warn(f"WebSocket connect failed (ssl={use_ssl}): {e}")
        raise last_error if last_error else ValueError("Failed to connect to WebSocket")

    async def _open_connection(self, use_ssl: bool) -> None:
        """Open the socket and perform the WebSocket handshake."""
        if use_ssl:
            if ssl is None:
                raise ValueError("HTTPS not supported - ssl module not available")
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.verify_mode = ssl.CERT_NONE
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port, ssl=ssl_context
            )
        else:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

        key = b2a_base64(urandom(16)).strip().decode()
        request = (
            "GET /api/websocket HTTP/1.1\r\n"
            "Host: {}:{}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Key: {}\r\n\r\n"
        ).format(self.host, self.port, key)
        await self.writer.awrite(request.encode("latin-1"))

        status_line = await self.reader.readline()
        if not status_line:
            raise ValueError("No response from WebSocket server")
        parts = status_line.split(None, 2)
        if len(parts) < 2 or int(parts[1]) != 101:
            raise ValueError(f"WebSocket upgrade failed: {status_line}")

        while True:
            line = await self.reader.readline()
            if not line or line == b"\r\n":
                break

    async def authenticate(self) -> None:
        """Perform Home Assistant token authentication over WebSocket."""
        msg = await self.receive_json()
        if msg.get("type") == "auth_required":
            await self.send_json({"type": "auth", "access_token": self.token})
            auth_reply = await self.receive_json()
            if auth_reply.get("type") != "auth_ok":
                raise ValueError(f"Auth failed: {auth_reply}")
            self.log.info("WebSocket auth ok")
        elif msg.get("type") == "auth_ok":
            self.log.info("WebSocket auth ok")
        else:
            raise ValueError(f"Unexpected auth message: {msg}")

    async def subscribe_events(self, event_type: str | None = None) -> int:
        """Subscribe to Home Assistant events and return the subscription id."""
        payload = {"id": self._message_id, "type": "subscribe_events"}
        if event_type:
            payload["event_type"] = event_type
        await self.send_json(payload)
        message_id = self._message_id
        self._message_id += 1
        return message_id

    async def send_json(self, payload) -> None:
        """Send a JSON payload over the WebSocket connection."""
        data = dumps(payload)
        await self._send_frame(data)

    async def receive_json(self) -> dict:
        """Receive a JSON message and update activity time."""
        data = await self._read_text_frame()
        if not data:
            return {}
        msg = loads(data)
        if msg.get("type") == "pong":
            self._last_pong_ms = ticks_ms()
        return msg

    async def listen(self, handler) -> None:
        """Continuously receive messages and invoke handler."""
        while True:
            msg = await self.receive_json()
            if msg:
                await handler(msg)

    async def listen_forever(
        self,
        handler,
        event_type: str | None = None
    ) -> None:
        """Reconnect forever and dispatch events to handler."""
        backoff = self.reconnect_initial_delay_s
        while True:
            listen_task = None
            keepalive_task = None
            try:
                await self.connect()
                await self.authenticate()
                if event_type is not None:
                    await self.subscribe_events(event_type)
                listen_task = asyncio.create_task(self.listen(handler))
                keepalive_task = asyncio.create_task(self._keepalive_loop())
                while True:
                    if listen_task.done() or keepalive_task.done():
                        break
                    await asyncio.sleep(0)

                if listen_task.done():
                    if not keepalive_task.done():
                        keepalive_task.cancel()
                    try:
                        await listen_task
                    except Exception as e:
                        raise e
                elif keepalive_task.done():
                    if not listen_task.done():
                        listen_task.cancel()
                    try:
                        await keepalive_task
                    except Exception as e:
                        raise e
            except Exception as e:
                self.log.warn(f"WebSocket error: {e}")
            finally:
                if listen_task is not None and not listen_task.done():
                    listen_task.cancel()
                if keepalive_task is not None and not keepalive_task.done():
                    keepalive_task.cancel()
                if listen_task is not None:
                    try:
                        await listen_task
                    except Exception:
                        pass
                if keepalive_task is not None:
                    try:
                        await keepalive_task
                    except Exception:
                        pass
                await self.close()

            self.log.info(f"Reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.reconnect_max_delay_s)

    async def close(self) -> None:
        """Close the WebSocket connection gracefully."""
        if self.writer:
            try:
                await self._send_close()
            except Exception:
                pass
            try:
                close_method = getattr(self.writer, "aclose", None)
                if callable(close_method):
                    result = close_method()
                    if asyncio.iscoroutine(result):
                        await result
                else:
                    close_method = getattr(self.writer, "close", None)
                    if callable(close_method):
                        close_method()
                    wait_closed = getattr(self.writer, "wait_closed", None)
                    if callable(wait_closed):
                        result = wait_closed()
                        if asyncio.iscoroutine(result):
                            await result
            except Exception:
                pass
        self.connected = False
        self.reader = None
        self.writer = None

    async def _keepalive_loop(self) -> None:
        """Send periodic pings and enforce a timeout window."""
        while self.is_open():
            ping_sent_ms = ticks_ms()
            await self.send_json({"id": self._message_id, "type": "ping"})
            self._message_id += 1
            while self.is_open():
                if ticks_diff(ticks_ms(), ping_sent_ms) > (self.pong_timeout_s * 1000):
                    raise ValueError("WebSocket pong timeout")
                if ticks_diff(self._last_pong_ms, ping_sent_ms) >= 0:
                    break
                await asyncio.sleep(0.1)
            await asyncio.sleep(self.ping_interval_s)

    async def _send_close(self) -> None:
        """Send a WebSocket close frame."""
        await self._send_frame(b"", opcode=0x8)

    async def _send_frame(self, payload, opcode: int = 0x1) -> None:
        """Encode and send a WebSocket frame with masking."""
        if not self.writer:
            raise ValueError("WebSocket not connected")
        if isinstance(payload, bytes):
            payload_bytes = payload
        else:
            payload_bytes = str(payload).encode("utf-8")
        length = len(payload_bytes)

        first_byte = 0x80 | (opcode & 0x0F)
        mask_bit = 0x80
        header = bytearray()
        header.append(first_byte)

        if length <= 125:
            header.append(mask_bit | length)
        elif length <= 0xFFFF:
            header.append(mask_bit | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(mask_bit | 127)
            header.extend(length.to_bytes(8, "big"))

        mask_key = urandom(4)
        header.extend(mask_key)

        masked = bytearray(payload_bytes)
        for i in range(length):
            masked[i] ^= mask_key[i % 4]

        await self.writer.awrite(header)
        if length:
            await self.writer.awrite(masked)

    async def _read_exact(self, nbytes: int) -> bytes:
        """Read exactly nbytes from the socket."""
        data = b""
        while len(data) < nbytes:
            if self.reader is None:
                raise ValueError("WebSocket not connected")
            chunk = await self.reader.read(nbytes - len(data))
            if not chunk:
                raise ValueError("WebSocket connection closed")
            data += chunk
        return data

    async def _read_frame(self) -> tuple:
        """Read a raw WebSocket frame and return (opcode, payload)."""
        if not self.reader:
            raise ValueError("WebSocket not connected")

        first_two = await self._read_exact(2)
        b1, b2 = first_two[0], first_two[1]
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        length = b2 & 0x7F

        if length == 126:
            length_bytes = await self._read_exact(2)
            length = int.from_bytes(length_bytes, "big")
        elif length == 127:
            length_bytes = await self._read_exact(8)
            length = int.from_bytes(length_bytes, "big")

        mask_key = b""
        if masked:
            mask_key = await self._read_exact(4)

        payload = await self._read_exact(length) if length > 0 else b""
        if masked and length > 0:
            unmasked = bytearray(payload)
            for i in range(length):
                unmasked[i] ^= mask_key[i % 4]
            payload = bytes(unmasked)

        return opcode, payload

    async def _read_text_frame(self) -> str:
        """Read until a text frame is received, handling control frames."""
        while True:
            opcode, payload = await self._read_frame()
            if opcode == 0x8:
                raise ValueError("WebSocket closed by server")
            if opcode == 0x9:
                await self._send_frame(payload, opcode=0xA)
                continue
            if opcode == 0xA:
                continue
            if opcode != 0x1:
                continue
            return payload.decode("utf-8")
