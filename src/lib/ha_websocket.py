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
try:
    import gc
except ImportError:
    gc = None


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
        read_timeout_s: int = 10,
        listen_timeout_s: int = 30,
        poll_interval_s: float = 0.05,
        reconnect_initial_delay_s: int = 1,
        reconnect_max_delay_s: int = 30
    ) -> None:
        """Initialize the WebSocket client and keepalive settings."""
        self.log = uLogger("HA-WS")
        self.wifi = network
        self.host = HA_HOST
        try:
            self.port = int(HA_PORT)
        except Exception as e:
            raise ValueError(f"Invalid HA_PORT: {HA_PORT}") from e
        self.token = HA_TOKEN
        self.reader = None
        self.writer = None
        self.connected = False
        self.use_ssl = False
        self._message_id = 1
        self.ping_interval_s = ping_interval_s
        self.pong_timeout_s = pong_timeout_s
        self.read_timeout_s = read_timeout_s
        self.listen_timeout_s = listen_timeout_s
        self.poll_interval_s = poll_interval_s
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
        reader = None
        writer = None
        try:
            if use_ssl:
                if ssl is None:
                    raise ValueError("HTTPS not supported - ssl module not available")
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.verify_mode = ssl.CERT_NONE
                reader, writer = await asyncio.open_connection(
                    self.host, self.port, ssl=ssl_context
                )
            else:
                reader, writer = await asyncio.open_connection(self.host, self.port)

            key = b2a_base64(urandom(16)).strip().decode()
            request = (
                "GET /api/websocket HTTP/1.1\r\n"
                "Host: {}:{}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Key: {}\r\n\r\n"
            ).format(self.host, self.port, key)
            await writer.awrite(request.encode("latin-1"))

            status_line = await reader.readline()
            if not status_line:
                raise ValueError("No response from WebSocket server")
            parts = status_line.split(None, 2)
            if len(parts) < 2 or int(parts[1]) != 101:
                raise ValueError(f"WebSocket upgrade failed: {status_line}")

            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break

            self.reader = reader
            self.writer = writer
        except Exception:
            if writer is not None:
                try:
                    close_method = getattr(writer, "aclose", None)
                    if callable(close_method):
                        result = close_method()
                        if asyncio.iscoroutine(result):
                            await result
                    else:
                        close_method = getattr(writer, "close", None)
                        if callable(close_method):
                            close_method()
                except Exception as e:
                    self.log.warn(f"Error while closing failed WS connection: {e}")
            raise

    async def authenticate(self) -> None:
        """Perform Home Assistant token authentication over WebSocket."""
        msg = await self.receive_json()
        if msg is None:
            raise ValueError("Auth failed: no response received")
        if msg.get("type") == "auth_required":
            await self.send_json({"type": "auth", "access_token": self.token})
            auth_reply = await self.receive_json()
            if auth_reply is None:
                raise ValueError("Auth failed: no response received")
            if auth_reply.get("type") != "auth_ok":
                raise ValueError(f"Auth failed: {auth_reply}")
            self.log.info("WebSocket auth ok")
        elif msg.get("type") == "auth_ok":
            self.log.info("WebSocket auth ok")
        else:
            raise ValueError(f"Unexpected auth message: {msg}")

    async def subscribe_events(
        self,
        event_type: str | None = None,
        wait_for_result: bool = False,
        timeout_s: int = 10
    ) -> int:
        """Subscribe to Home Assistant events and return the subscription id.

        Use wait_for_result=True to validate the HA subscription response.
        """
        payload = {"id": self._message_id, "type": "subscribe_events"}
        if event_type:
            payload["event_type"] = event_type
        await self.send_json(payload)
        message_id = self._message_id
        self._message_id += 1

        if wait_for_result:
            await self._wait_for_result(message_id, timeout_s)

        return message_id

    async def _wait_for_result(self, message_id: int, timeout_s: int = 10) -> None:
        """Wait for a matching Home Assistant result response."""
        start_ms = ticks_ms()
        while True:
            if ticks_diff(ticks_ms(), start_ms) > (timeout_s * 1000):
                raise ValueError("Timed out waiting for subscribe_events result")
            msg = await self.receive_json()
            if msg is None:
                continue
            if msg.get("type") == "result" and msg.get("id") == message_id:
                if not msg.get("success", False):
                    raise ValueError(f"subscribe_events failed: {msg}")
                return

    async def send_json(self, payload) -> None:
        """Send a JSON payload over the WebSocket connection."""
        data = dumps(payload)
        await self._send_frame(data)

    async def receive_json(self):
        """Receive a JSON message and update activity time."""
        data = await self._read_text_frame()
        if not data:
            return None
        msg = loads(data)
        if msg.get("type") == "pong":
            self._last_pong_ms = ticks_ms()
        return msg

    async def listen(self, handler) -> None:
        """Continuously receive messages and invoke handler."""
        last_msg_ms = ticks_ms()
        while True:
            msg = await self.receive_json()
            if msg is None:
                if ticks_diff(ticks_ms(), last_msg_ms) > (self.listen_timeout_s * 1000):
                    raise ValueError("WebSocket listen timeout")
                await asyncio.sleep(self.poll_interval_s)
                continue
            last_msg_ms = ticks_ms()
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
                backoff = self.reconnect_initial_delay_s
                if event_type is not None:
                    await self.subscribe_events(event_type, wait_for_result=True)
                listen_task = asyncio.create_task(self.listen(handler))
                keepalive_task = asyncio.create_task(self._keepalive_loop())
                while True:
                    if listen_task.done() or keepalive_task.done():
                        break
                    await asyncio.sleep(self.poll_interval_s)

                listen_exc = None
                keepalive_exc = None
                if listen_task.done():
                    try:
                        await listen_task
                    except Exception as e:
                        listen_exc = e
                if keepalive_task.done():
                    try:
                        await keepalive_task
                    except Exception as e:
                        keepalive_exc = e

                if not keepalive_task.done():
                    keepalive_task.cancel()
                if not listen_task.done():
                    listen_task.cancel()

                if listen_exc is not None:
                    raise listen_exc
                if keepalive_exc is not None:
                    raise keepalive_exc
            except MemoryError as e:
                self.log.error(f"WebSocket memory error: {e}")
                if gc is not None:
                    gc.collect()
                    self.log.info("Garbage collection triggered after memory error")
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
                    except Exception as e:
                        self.log.warn(f"Error while awaiting listen task cleanup: {e}")
                if keepalive_task is not None:
                    try:
                        await keepalive_task
                    except Exception as e:
                        self.log.warn(f"Error while awaiting keepalive task cleanup: {e}")
                await self.close()

            self.log.info(f"Reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.reconnect_max_delay_s)

    async def close(self) -> None:
        """Close the WebSocket connection gracefully."""
        if self.writer:
            try:
                await self._send_close()
            except Exception as e:
                self.log.warn(f"Error while sending WebSocket close frame: {e}")
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
            except Exception as e:
                self.log.warn(f"Error while closing WebSocket writer: {e}")
        self.connected = False
        self.reader = None
        self.writer = None

    async def _keepalive_loop(self) -> None:
        """Send periodic pings and enforce a timeout window."""
        while self.is_open():
            ping_sent_ms = ticks_ms()
            await self.send_json({"id": self._message_id, "type": "ping"})
            self._message_id = self._next_message_id()
            while self.is_open():
                if ticks_diff(ticks_ms(), ping_sent_ms) > (self.pong_timeout_s * 1000):
                    raise ValueError("WebSocket pong timeout")
                if ticks_diff(self._last_pong_ms, ping_sent_ms) >= 0:
                    break
                await asyncio.sleep(self.poll_interval_s)
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

    def _next_message_id(self) -> int:
        """Return next message id, wrapping to avoid unbounded growth."""
        next_id = self._message_id + 1
        if next_id > 2000000000:
            next_id = 1
        return next_id

    async def _read_exact(self, nbytes: int) -> bytes:
        """Read exactly nbytes from the socket with a timeout."""
        data = b""
        start_ms = ticks_ms()
        empty_reads = 0
        while len(data) < nbytes:
            if self.reader is None:
                raise ValueError("WebSocket not connected")
            chunk = await self.reader.read(nbytes - len(data))
            if not chunk:
                if ticks_diff(ticks_ms(), start_ms) > (self.read_timeout_s * 1000):
                    raise ValueError("WebSocket read timeout")
                empty_reads += 1
                sleep_time = 0.05 * empty_reads
                if sleep_time > 0.5:
                    sleep_time = 0.5
                await asyncio.sleep(sleep_time)
                continue
            empty_reads = 0
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
