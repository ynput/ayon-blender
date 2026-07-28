#!/usr/bin/env python
"""Example usage of the IPC system for testing and demonstration.

This script shows:
1. Starting an IPC server (simulating Blender side)
2. Connecting a client (simulating external UI side)
3. Sending requests and receiving responses
4. Publishing events
5. Handling reconnection

To run this example:
    python examples/ipc_usage_example.py
"""

import sys
import time
import threading
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ipc_bridge import IPCServer
from ipc_client import IPCClient


def example_basic_usage():
    """Example 1: Basic server-client communication."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Basic Server-Client Communication")
    print("=" * 70 + "\n")

    # Create and start server
    server = IPCServer()
    port = server.start()
    token = server.get_session_token()

    logger.info(f"Server started on port {port}")

    # Register a simple handler
    def handle_echo(params):
        message = params.get("message", "")
        return f"Echo: {message}"

    server.register_handler("echo", handle_echo)

    # Create client and connect
    client = IPCClient(host="127.0.0.1", port=port, session_token=token)
    if not client.connect():
        logger.error("Failed to connect")
        return

    logger.info("Client connected")

    # Send request
    success, result, error = client.send_request_wait(
        method="echo",
        params={"message": "Hello from external UI!"}
    )

    if success:
        logger.info(f"Response: {result}")
    else:
        logger.error(f"Error: {error}")

    # Cleanup
    client.disconnect()
    server.stop()


def example_async_requests():
    """Example 2: Async requests with callbacks."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Async Requests with Callbacks")
    print("=" * 70 + "\n")

    server = IPCServer()
    port = server.start()
    token = server.get_session_token()

    def handle_long_task(params):
        """Simulate a long-running task."""
        duration = params.get("duration", 2.0)
        time.sleep(duration)
        return f"Task completed in {duration}s"

    server.register_handler("long_task", handle_long_task)

    client = IPCClient(host="127.0.0.1", port=port, session_token=token)
    client.connect()

    responses = {}

    def on_response(ok, result, error):
        responses["result"] = (ok, result, error)

    # Send async request
    request_id = client.send_request(
        method="long_task",
        params={"duration": 1.0},
        timeout_sec=5.0,
        callback=on_response
    )

    logger.info(f"Sent async request: {request_id}")

    # Wait for response (with timeout)
    for i in range(10):
        if "result" in responses:
            ok, result, error = responses["result"]
            logger.info(f"Response received: ok={ok}, result={result}")
            break
        logger.info(f"Waiting for response... ({i+1}/10)")
        time.sleep(0.5)

    client.disconnect()
    server.stop()


def example_events():
    """Example 3: Publishing and subscribing to events."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Events (Publish-Subscribe)")
    print("=" * 70 + "\n")

    server = IPCServer()
    port = server.start()
    token = server.get_session_token()

    client = IPCClient(host="127.0.0.1", port=port, session_token=token)
    client.connect()

    events_received = []

    def on_render_event(payload):
        events_received.append(payload)
        logger.info(f"Event received: {payload}")

    # Subscribe to event
    client.subscribe("render_started", on_render_event)
    client.subscribe("render_finished", on_render_event)

    logger.info("Subscribed to render events")

    # Publish events from server (simulate Blender)
    def publish_events():
        time.sleep(0.5)
        server.publish_event("render_started", {"scene": "Scene", "frame": 1})
        time.sleep(0.5)
        server.process_events()
        time.sleep(1.0)
        server.publish_event("render_finished", {"scene": "Scene", "frames": 100})
        server.process_events()

    # Run publisher in background
    pub_thread = threading.Thread(target=publish_events)
    pub_thread.start()

    # Wait for events
    for i in range(30):
        if len(events_received) >= 2:
            logger.info(f"All events received: {events_received}")
            break
        time.sleep(0.2)

    pub_thread.join()
    client.disconnect()
    server.stop()


def example_reconnection():
    """Example 4: Client reconnection after server restart."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Automatic Reconnection")
    print("=" * 70 + "\n")

    server = IPCServer()
    port = server.start()
    token = server.get_session_token()

    def handle_test(params):
        return "Test response"

    server.register_handler("test", handle_test)

    client = IPCClient(host="127.0.0.1", port=port, session_token=token)
    client.connect()

    # Send request
    success, result, _ = client.send_request_wait("test")
    logger.info(f"Before restart: {result}")

    # Stop server
    logger.info("Stopping server...")
    server.stop()
    time.sleep(1)

    logger.info("Client state: " + client.get_state())

    # Restart server
    logger.info("Restarting server...")
    server = IPCServer(port=port)
    port = server.start()
    server.register_handler("test", handle_test)

    # Client should reconnect
    client.reconnect_with_backoff()
    logger.info("Client state: " + client.get_state())

    if client.is_connected():
        success, result, _ = client.send_request_wait("test")
        logger.info(f"After restart: {result}")
    else:
        logger.warning("Reconnection failed")

    client.disconnect()
    server.stop()


def example_busy_detection():
    """Example 5: Detecting Blender busy state."""
    print("\n" + "=" * 70)
    print("EXAMPLE 5: Blender Busy Detection (Simulated)")
    print("=" * 70 + "\n")

    server = IPCServer()
    port = server.start()
    token = server.get_session_token()

    def handle_slow_operation(params):
        """Simulate a slow operation (rendering)."""
        logger.info("Server: Processing slow operation...")
        time.sleep(5.0)
        return "Done"

    server.register_handler("slow_op", handle_slow_operation)

    client = IPCClient(host="127.0.0.1", port=port, session_token=token)
    client.connect()

    # Send slow request
    request_id = client.send_request(
        method="slow_op",
        params={},
        timeout_sec=10.0,
    )

    logger.info("Sent slow operation request")

    # Check client state while operation is running
    for i in range(15):
        state = client.get_state()
        logger.info(f"Client state: {state} (iteration {i+1}/15)")
        time.sleep(0.5)

    client.disconnect()
    server.stop()


if __name__ == "__main__":
    print("\nBlender IPC System Examples")
    print("===========================")

    # Run examples
    example_basic_usage()
    time.sleep(1)

    example_async_requests()
    time.sleep(1)

    example_events()
    time.sleep(1)

    example_reconnection()
    time.sleep(1)

    example_busy_detection()

    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70 + "\n")


