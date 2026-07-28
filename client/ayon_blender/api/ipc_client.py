"""Qt-side IPC client for communicating with Blender.

This module provides a client for Qt UI processes to communicate with Blender
via the IPC bridge. Features:
- Automatic reconnection with backoff
- Request queuing and idempotency
- Connection state tracking
- Event subscription and callbacks
- Graceful handling of Blender unresponsiveness
"""

import socket
import time
import logging
import threading
import uuid
from typing import Optional, Dict, Any, Callable, List, Tuple
from pathlib import Path
import sys

# Add current directory to path for imports
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

try:
    from .ipc_protocol import (
        Message, MessageType, HelloMessage, RequestMessage, ResponseMessage,
        EventMessage, PingMessage, PongMessage, parse_message
    )
except ImportError:
    # Fallback for when module is run as script
    from ipc_protocol import (
        Message, MessageType, HelloMessage, RequestMessage, ResponseMessage,
        EventMessage, PingMessage, PongMessage, parse_message
    )

logger = logging.getLogger(__name__)


class ConnectionState:
    """Tracks connection state and provides status info."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    BLENDER_BUSY = "blender_busy"


class PendingRequest:
    """Tracks a pending request with timeout and callback."""

    def __init__(
        self,
        request_id: str,
        method: str,
        timeout_sec: float = 30.0,
        idempotency_key: Optional[str] = None,
    ):
        self.request_id = request_id
        self.method = method
        self.timeout_sec = timeout_sec
        self.idempotency_key = idempotency_key
        self.submitted_at = time.time()
        self.callback: Optional[Callable[[bool, Any, Optional[str]], None]] = None
        self.done = False

    def is_expired(self) -> bool:
        """Check if request has timed out."""
        elapsed = time.time() - self.submitted_at
        return elapsed > self.timeout_sec

    def mark_done(self):
        """Mark request as completed."""
        self.done = True


class IPCClient:
    """Client for connecting to Blender IPC bridge from Qt processes.

    Handles:
    - Connection and reconnection with exponential backoff
    - Async requests with optional callbacks
    - Event subscriptions
    - Blender busy state detection
    - Graceful disconnection handling
    """

    # Reconnection backoff: 0.5s -> 1s -> 2s -> 5s (cap)
    RECONNECT_DELAYS = [0.5, 1.0, 2.0, 5.0]

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        session_token: str = "",
        session_id: Optional[str] = None,
    ):
        """Initialize IPC client.

        Args:
            host: Server host (should be 127.0.0.1)
            port: Server port
            session_token: Authentication token from Blender
            session_id: Optional session identifier
        """
        self.host = host
        self.port = port
        self.session_token = session_token
        self.session_id = session_id or str(uuid.uuid4())[:8]

        self.socket: Optional[socket.socket] = None
        self.state = ConnectionState.DISCONNECTED
        self.connected = False

        self.pending_requests: Dict[str, PendingRequest] = {}
        self.response_callbacks: Dict[str, Callable] = {}
        self.event_subscribers: Dict[str, List[Callable]] = {}

        self.reconnect_attempts = 0
        self.last_heartbeat = time.time()
        self.blender_unresponsive_since: Optional[float] = None

        self._lock = threading.RLock()
        self._receiver_thread: Optional[threading.Thread] = None
        self._running = False
        self._recv_buffer = b""

    def connect(self) -> bool:
        """Establish connection to Blender IPC server.

        Returns:
            True if connection successful, False otherwise
        """
        if self.connected:
            return True

        try:
            logger.info(
                f"Connecting to Blender IPC at {self.host}:{self.port} "
                f"(session: {self.session_id})"
            )

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((self.host, self.port))

            self.state = ConnectionState.CONNECTING

            # Send HELLO message
            hello = HelloMessage(
                session_token=self.session_token,
                session_id=self.session_id
            )
            self._send_message(hello)

            # Receive HELLO_ACK
            ack_json = self._receive_line()
            if not ack_json:
                raise RuntimeError("No HELLO_ACK received")

            ack = parse_message(ack_json)
            if ack.type != MessageType.HELLO_ACK:
                raise RuntimeError(f"Expected HELLO_ACK, got {ack.type}")

            self.connected = True
            self.state = ConnectionState.CONNECTED
            self.reconnect_attempts = 0
            self.blender_unresponsive_since = None
            self.last_heartbeat = time.time()

            logger.info(f"Connected to Blender (session: {self.session_id})")

            # Start receiver thread
            if not self._running:
                self._running = True
                self._receiver_thread = threading.Thread(
                    target=self._receiver_loop, daemon=True
                )
                self._receiver_thread.start()

            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.connected = False
            self.state = ConnectionState.DISCONNECTED
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            return False

    def disconnect(self):
        """Disconnect from Blender."""
        self._running = False
        self.connected = False
        self.state = ConnectionState.DISCONNECTED

        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        if self._receiver_thread:
            self._receiver_thread.join(timeout=5)
        self._receiver_thread = None

    def reconnect_with_backoff(self):
        """Attempt reconnection with exponential backoff."""
        if self.connected:
            return

        delay_index = min(self.reconnect_attempts, len(self.RECONNECT_DELAYS) - 1)
        delay = self.RECONNECT_DELAYS[delay_index]

        logger.info(
            f"Reconnecting (attempt {self.reconnect_attempts + 1}, "
            f"delay {delay}s)..."
        )

        time.sleep(delay)
        success = self.connect()
        if success:
            self.reconnect_attempts = 0
        else:
            self.reconnect_attempts += 1

    def send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_sec: float = 30.0,
        callback: Optional[Callable[[bool, Any, Optional[str]], None]] = None,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """Send an async request to Blender.

        Args:
            method: Method name to call in Blender
            params: Parameters for the method
            timeout_sec: Request timeout in seconds
            callback: Optional callback(ok, result, error_msg)
            idempotency_key: For request deduplication

        Returns:
            Request ID
        """
        if not self.connected:
            error_msg = "Not connected to Blender"
            if callback:
                callback(False, None, error_msg)
            raise RuntimeError(error_msg)

        if params is None:
            params = {}

        request_id = str(uuid.uuid4())
        req = RequestMessage(
            method=method,
            params=params,
            request_id=request_id,
            timeout_sec=timeout_sec,
            idempotency_key=idempotency_key,
        )

        with self._lock:
            self.pending_requests[request_id] = PendingRequest(
                request_id=request_id,
                method=method,
                timeout_sec=timeout_sec,
                idempotency_key=idempotency_key,
            )
            if callback:
                self.response_callbacks[request_id] = callback

        try:
            self._send_message(req)
            logger.debug(f"Sent request {request_id}: {method}")
            return request_id
        except Exception as e:
            logger.error(f"Failed to send request: {e}")
            with self._lock:
                self.pending_requests.pop(request_id, None)
                self.response_callbacks.pop(request_id, None)
            if callback:
                callback(False, None, str(e))
            raise

    def send_request_wait(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_sec: float = 30.0,
    ) -> Tuple[bool, Any, Optional[str]]:
        """Send a request and wait for response (blocking).

        Args:
            method: Method name
            params: Parameters
            timeout_sec: Timeout in seconds

        Returns:
            (success, result, error_msg)
        """
        done_event = threading.Event()
        result_holder = {"ok": False, "result": None, "error": None}

        def callback(ok, result, error):
            result_holder["ok"] = ok
            result_holder["result"] = result
            result_holder["error"] = error
            done_event.set()

        self.send_request(
            method=method,
            params=params,
            timeout_sec=timeout_sec,
            callback=callback,
        )

        if done_event.wait(timeout=timeout_sec + 5):
            return (
                result_holder["ok"],
                result_holder["result"],
                result_holder["error"],
            )
        else:
            return False, None, "Request timeout"

    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], None]):
        """Subscribe to an event topic.

        Args:
            topic: Event topic name
            callback: Called when event is received
        """
        with self._lock:
            if topic not in self.event_subscribers:
                self.event_subscribers[topic] = []
            self.event_subscribers[topic].append(callback)

        logger.debug(f"Subscribed to event: {topic}")

    def unsubscribe(self, topic: str, callback: Callable):
        """Unsubscribe from an event topic."""
        with self._lock:
            if topic in self.event_subscribers:
                try:
                    self.event_subscribers[topic].remove(callback)
                except ValueError:
                    pass

    def get_state(self) -> str:
        """Get current connection state."""
        return self.state

    def is_connected(self) -> bool:
        """Check if connected."""
        return self.connected

    def is_blender_busy(self) -> bool:
        """Check if Blender is detected as busy (unresponsive)."""
        return self.state == ConnectionState.BLENDER_BUSY

    def _send_message(self, msg: Message):
        """Send message to server."""
        if not self.socket:
            raise RuntimeError("Not connected")

        json_str = msg.to_json()
        self.socket.sendall((json_str + "\n").encode("utf-8"))
        self.last_heartbeat = time.time()

    def _receive_line(self) -> Optional[str]:
        """Receive a single line of JSON."""
        if not self.socket:
            return None

        while True:
            if b"\n" in self._recv_buffer:
                line, self._recv_buffer = self._recv_buffer.split(b"\n", 1)
                return line.decode("utf-8").strip()
            try:
                chunk = self.socket.recv(4096)
                if not chunk:
                    return None
                self._recv_buffer += chunk
            except socket.timeout:
                raise

    def _receiver_loop(self):
        """Receive and process messages (runs in background thread)."""
        while self._running and self.connected:
            try:
                if not self.socket:
                    break

                self.socket.settimeout(5.0)
                msg_json = self._receive_line()

                if not msg_json:
                    logger.info("Blender disconnected")
                    self.connected = False
                    self.state = ConnectionState.DISCONNECTED
                    break

                msg = parse_message(msg_json)
                self._handle_message(msg)

            except socket.timeout:
                # Check for pending request timeouts
                self._check_request_timeouts()

                # Check heartbeat (detect Blender busy)
                if time.time() - self.last_heartbeat > 60:
                    if self.state != ConnectionState.BLENDER_BUSY:
                        logger.warning("Blender unresponsive for 60s, marking busy")
                        self.state = ConnectionState.BLENDER_BUSY
                        self.blender_unresponsive_since = time.time()
                continue

            except Exception as e:
                if self._running:
                    logger.error(f"Receiver loop error: {e}")
                self.connected = False
                self.state = ConnectionState.DISCONNECTED
                break

    def _handle_message(self, msg: Message):
        """Handle incoming message."""
        try:
            if msg.type == MessageType.RESPONSE:
                self._handle_response(msg)
            elif msg.type == MessageType.EVENT:
                self._handle_event(msg)
            elif msg.type == MessageType.PING:
                self._send_message(PongMessage())
            elif msg.type == MessageType.PONG:
                # Mark as responsive
                if self.state == ConnectionState.BLENDER_BUSY:
                    logger.info("Blender responsive again")
                    self.state = ConnectionState.CONNECTED
                    self.blender_unresponsive_since = None
                self.last_heartbeat = time.time()
            else:
                logger.warning(f"Unexpected message type: {msg.type}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _handle_response(self, resp: ResponseMessage):
        """Handle response message."""
        request_id = resp.data.get("id")
        ok = resp.data.get("ok", False)
        result = resp.data.get("result")
        error = resp.data.get("error")

        logger.debug(f"Response for request {request_id}: ok={ok}")

        with self._lock:
            self.pending_requests.pop(request_id, None)
            callback = self.response_callbacks.pop(request_id, None)

        if callback:
            try:
                callback(ok, result, error)
            except Exception as e:
                logger.error(f"Error in response callback: {e}")

    def _handle_event(self, event: EventMessage):
        """Handle event message."""
        topic = event.data.get("topic")
        payload = event.data.get("payload", {})

        logger.debug(f"Event received: {topic}")

        with self._lock:
            subscribers = self.event_subscribers.get(topic, [])

        for callback in subscribers:
            try:
                callback(payload)
            except Exception as e:
                logger.error(f"Error in event subscriber: {e}")

    def _check_request_timeouts(self):
        """Check for expired requests and invoke callbacks."""
        expired = []
        with self._lock:
            for request_id, pending in list(self.pending_requests.items()):
                if pending.is_expired() and not pending.done:
                    expired.append(request_id)
                    pending.mark_done()

        for request_id in expired:
            with self._lock:
                callback = self.response_callbacks.pop(request_id, None)

            if callback:
                try:
                    callback(False, None, "Request timeout")
                except Exception as e:
                    logger.error(f"Error in timeout callback: {e}")





