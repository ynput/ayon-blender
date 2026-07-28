"""Blender-side IPC bridge for external UI communication.

This module implements a TCP server that listens for connections from external
Qt UI processes. It handles:
- Session management and authentication
- Async request processing via main-thread callbacks
- Event publishing when Blender state changes
- Graceful handling of Blender unresponsiveness (render/processing)
- Automatic reconnect support
"""

import os
import sys
import socket
import logging
import threading
import collections
from typing import Optional, Dict, Any, Callable
from pathlib import Path

# Add current directory to path for imports
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

try:
    from .ipc_protocol import (
        Message, MessageType, HelloMessage, HelloAckMessage, ResponseMessage,
        EventMessage, RequestMessage, PingMessage, PongMessage, parse_message
    )
except ImportError:
    # Fallback for when module is run as script
    from ipc_protocol import (
        Message, MessageType, HelloMessage, HelloAckMessage, ResponseMessage,
        EventMessage, RequestMessage, PingMessage, PongMessage, parse_message
    )

logger = logging.getLogger(__name__)


class IPCServer:
    """TCP server for IPC communication between Blender and external UIs.

    This is the Blender-side server. It listens for connections and dispatches
    requests to Blender via main-thread callbacks.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        """Initialize IPC server.

        Args:
            host: Bind address (127.0.0.1 only for security)
            port: Port number (0 = auto-select)
        """
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.server_thread: Optional[threading.Thread] = None
        self.clients: Dict[str, "IPCClientConnection"] = {}
        self.session_token = os.urandom(16).hex()
        self.request_handlers: Dict[str, Callable] = {}
        self.event_queue = collections.deque()
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.response_callbacks: Dict[str, Callable] = {}
        self._lock = threading.RLock()

    def start(self) -> int:
        """Start the IPC server.

        Returns:
            Port number the server is listening on
        """
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        actual_host, actual_port = self.server_socket.getsockname()
        self.port = actual_port

        self.running = True
        self.server_thread = threading.Thread(
            target=self._server_loop, daemon=True
        )
        self.server_thread.start()

        logger.info(
            f"IPC server started on {actual_host}:{actual_port} "
            f"(token: {self.session_token[:8]}...)"
        )
        return actual_port

    def stop(self):
        """Stop the IPC server."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

        # Close all client connections
        with self._lock:
            for client in list(self.clients.values()):
                try:
                    client.close()
                except Exception:
                    pass

        if self.server_thread:
            self.server_thread.join(timeout=5)

        logger.info("IPC server stopped")

    def register_handler(self, method: str, handler: Callable):
        """Register a request handler.

        Args:
            method: Method name (e.g. 'show_creator')
            handler: Callable that accepts (params: Dict) -> Any
        """
        self.request_handlers[method] = handler
        logger.debug(f"Registered handler for method: {method}")

    def publish_event(self, topic: str, payload: Optional[Dict[str, Any]] = None):
        """Publish an event to all connected clients.

        Args:
            topic: Event topic (e.g. 'render_started')
            payload: Event data
        """
        if payload is None:
            payload = {}

        event = EventMessage(topic=topic, payload=payload)
        with self._lock:
            self.event_queue.append(event)

    def send_event_to_all(self, topic: str, payload: Optional[Dict[str, Any]] = None):
        """Publish event to all clients immediately."""
        self.publish_event(topic, payload)
        self.process_events()

    def get_session_token(self) -> str:
        """Get the session token for validating client connections."""
        return self.session_token

    def process_events(self) -> bool:
        """Process pending events and dispatch to clients.

        Should be called from Blender main thread via timer callback.

        Returns:
            True if there were events to process
        """
        events_processed = False

        with self._lock:
            while self.event_queue:
                event = self.event_queue.popleft()
                # Send to all connected clients
                for client in list(self.clients.values()):
                    try:
                        client.send_message(event)
                    except Exception as e:
                        logger.warning(f"Failed to send event to client: {e}")
                events_processed = True

        return events_processed

    def _server_loop(self):
        """Main server loop (runs in background thread)."""
        while self.running:
            try:
                # Accept connections with timeout to allow check of self.running
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, addr = self.server_socket.accept()
                except socket.timeout:
                    continue

                logger.info(f"Client connected from {addr}")
                client = IPCClientConnection(self, client_socket, addr)

                # Start client handler in separate thread
                client_thread = threading.Thread(
                    target=client.handle, daemon=True
                )
                client_thread.start()

            except Exception as e:
                if self.running:
                    logger.error(f"Server loop error: {e}", exc_info=True)
                break

        logger.debug("Server loop exited")


class IPCClientConnection:
    """Represents a single client connection to the IPC server."""

    def __init__(self, server: IPCServer, socket_obj: socket.socket, addr: tuple):
        self.server = server
        self.socket = socket_obj
        self.addr = addr
        self.session_id: Optional[str] = None
        self.authenticated = False
        self._lock = threading.RLock()
        self._connected = True
        self._recv_buffer = b""

    def handle(self):
        """Handle client connection (runs in separate thread)."""
        try:
            self.socket.settimeout(30.0)

            # Wait for HELLO message
            hello_json = self._receive_line()
            if not hello_json:
                logger.warning(f"Client {self.addr} disconnected before HELLO")
                return

            try:
                hello_msg = parse_message(hello_json)
                if not isinstance(hello_msg, HelloMessage):
                    self._send_error("Expected HELLO message")
                    return

                # Validate session token
                if hello_msg.data.get("session_token") != self.server.session_token:
                    self._send_error("Invalid session token")
                    return

                self.session_id = str(hello_msg.data.get("session_id") or self.addr[1])
                self.authenticated = True

                with self.server._lock:
                    self.server.clients[self.session_id] = self

                # Send HELLO_ACK
                ack = HelloAckMessage(session_id=self.session_id)
                self._send_message(ack)
                logger.info(f"Client {self.addr} authenticated: {self.session_id}")

            except ValueError as e:
                self._send_error(f"Invalid HELLO message: {e}")
                return

            # Main message loop
            while self._connected:
                try:
                    msg_json = self._receive_line()
                    if not msg_json:
                        logger.debug(f"Client {self.addr} disconnected")
                        break

                    msg = parse_message(msg_json)
                    self._handle_message(msg)

                except socket.timeout:
                    # Client may be idle for long periods while Blender is busy.
                    continue

        except Exception as e:
            logger.error(f"Error handling client {self.addr}: {e}")
        finally:
            self.close()

    def _handle_message(self, msg: Message):
        """Handle incoming message."""
        try:
            if msg.type == MessageType.REQUEST:
                self._handle_request(msg)
            elif msg.type == MessageType.PING:
                self._send_message(PongMessage())
            elif msg.type == MessageType.PONG:
                # Keep-alive acknowledgement
                pass
            else:
                logger.warning(f"Unexpected message type: {msg.type}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _handle_request(self, req: RequestMessage):
        """Handle incoming request."""
        request_id = req.data.get("id")
        method = req.data.get("method")
        params = req.data.get("params", {})

        logger.debug(f"Handling request {request_id}: {method}")

        # Check if handler is registered
        handler = self.server.request_handlers.get(method)
        if not handler:
            response = ResponseMessage(
                request_id=request_id,
                ok=False,
                error=f"Unknown method: {method}"
            )
            self._send_message(response)
            return

        # Store request and callback
        def send_response(result=None, error=None):
            """Send response back to client."""
            response = ResponseMessage(
                request_id=request_id,
                ok=error is None,
                result=result,
                error=error
            )
            try:
                self._send_message(response)
            except Exception as e:
                logger.error(f"Failed to send response: {e}")

        try:
            # Call handler (may be queued to main thread by handler)
            result = handler(params)
            send_response(result=result)
        except Exception as e:
            logger.error(f"Handler error for {method}: {e}")
            send_response(error=str(e))

    def _send_message(self, msg: Message):
        """Send message to client."""
        with self._lock:
            if not self._connected:
                raise RuntimeError("Client disconnected")
            json_str = msg.to_json()
            self.socket.sendall((json_str + "\n").encode("utf-8"))

    def send_message(self, msg: Message):
        """Public method to send message to client."""
        self._send_message(msg)

    def _send_error(self, error_msg: str):
        """Send error message."""
        msg = Message(MessageType.ERROR, error=error_msg)
        try:
            self._send_message(msg)
        except Exception:
            pass

    def _receive_line(self) -> Optional[str]:
        """Receive a single line of JSON."""
        if not self._connected:
            return None

        while True:
            if b"\n" in self._recv_buffer:
                line, self._recv_buffer = self._recv_buffer.split(b"\n", 1)
                return line.decode("utf-8").strip()
            try:
                chunk = self.socket.recv(4096)
                if not chunk:
                    self._connected = False
                    return None
                self._recv_buffer += chunk
            except socket.timeout:
                raise

        return None

    def close(self):
        """Close the client connection."""
        with self._lock:
            self._connected = False
            try:
                self.socket.close()
            except Exception:
                pass

        # Unregister from server
        if self.session_id:
            with self.server._lock:
                self.server.clients.pop(self.session_id, None)


# Global server instance
_ipc_server: Optional[IPCServer] = None


def get_ipc_server() -> IPCServer:
    """Get or create the global IPC server instance."""
    global _ipc_server
    if _ipc_server is None:
        _ipc_server = IPCServer()
    return _ipc_server


def start_ipc_server() -> int:
    """Start the IPC server and return the port."""
    server = get_ipc_server()
    return server.start()


def stop_ipc_server():
    """Stop the IPC server."""
    global _ipc_server
    if _ipc_server:
        _ipc_server.stop()
        _ipc_server = None




