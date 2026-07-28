# Blender IPC Integration for External Qt UIs

This document describes the new inter-process communication (IPC) system for running Qt UIs in separate processes outside of Blender.

## Overview

Previously, AYON tools (Creator, Loader, Publisher, etc.) ran as Qt dialogs inside Blender's Python interpreter. This could cause issues when Blender was rendering or performing other long-running operations, as it would block the UI thread.

The new IPC system:
- **Separates UI from Blender**: Qt UIs run in a separate Python process
- **Handles unresponsiveness gracefully**: Detects when Blender is busy (rendering) and gracefully queues operations
- **Maintains communication reliability**: Automatic reconnection with exponential backoff
- **Provides event publishing**: Blender can publish events (render started/completed) to UI process

## Architecture

```
┌─────────────────────────────────────┐
│      Blender Process (Main)         │
│  ┌──────────────────────────────────┤
│  │ IPC Server (TCP 127.0.0.1:PORT)  │
│  │  - Listen for UI connections    │
│  │  - Dispatch requests to handlers │
│  │  - Publish render events        │
│  └──────────────────────────────────┤
│  - Main thread callback queue       │
│  - Render event handlers            │
└─────────────────────────────────────┘
         ↑                    ↓
      [TCP Socket] - JSON-based protocol
         ↑                    ↓
┌─────────────────────────────────────┐
│    External UI Process (Child)      │
│  ┌──────────────────────────────────┤
│  │ IPC Client                       │
│  │  - Connect to Blender IPC server │
│  │  - Send async requests           │
│  │  - Subscribe to events           │
│  └──────────────────────────────────┤
│  - Qt QApplication                  │
│  - Tool windows (Creator, Loader)   │
│  - Connection state tracking        │
└─────────────────────────────────────┘
```

## Loader split architecture

The loader now uses a split controller setup:

- Backend controller in Blender process:
  - `ayon-blender/ipc_communication/loader_ipc.py`
  - `BlenderLoaderBackendBridge` owns `ayon_core.tools.loader.LoaderController`
  - Executes all loader methods inside Blender main thread via `MainThreadItem`
  - Emits loader events as IPC event topic `loader_event`

- Frontend controller in external UI process:
  - `ayon-blender/ipc_communication/loader_ipc.py`
  - `RemoteLoaderFrontendController` is passed to `LoaderWindow`
  - Forwards method calls through IPC request `loader_call`
  - Receives `loader_event` payloads and dispatches callbacks locally

- External loader UI host glue:
  - `ayon-blender/client/ayon_blender/api/external_ui_host.py`
  - Intercepts `open_tool` for `loader` / `libraryloader`
  - Creates `LoaderWindow(controller=RemoteLoaderFrontendController(...))`

- Blender IPC handler registration:
  - `ayon-blender/client/ayon_blender/api/ops.py`
  - Registers request handler `loader_call`
  - Initializes `BlenderLoaderBackendBridge` when IPC starts

## Protocol

All communication uses JSON-based messages over TCP, one message per line (newline-delimited JSON).

### Message Types

#### HELLO (Client → Server)
```json
{
    "type": "hello",
    "session_token": "...",
    "session_id": "client-1",
    "version": "1.0"
}
```

#### HELLO_ACK (Server → Client)
```json
{
    "type": "hello_ack",
    "session_id": "client-1"
}
```

#### REQUEST (Client → Server)
```json
{
    "type": "request",
    "id": "req-uuid",
    "method": "show_tool",
    "params": {"tool": "creator", "tab": "create"},
    "timeout_sec": 30.0,
    "idempotency_key": "optional-key"
}
```

#### RESPONSE (Server → Client)
```json
{
    "type": "response",
    "id": "req-uuid",
    "ok": true,
    "result": "Tool creator opened",
    "error": null
}
```

#### EVENT (Server → Client)
```json
{
    "type": "event",
    "topic": "render_started",
    "payload": {"scene": "Scene"}
}
```

#### PING / PONG (Bidirectional)
Used for keep-alive and connection health checks.

## Usage

### Enable External UI Mode

In `ops.py`, set the flag:

```python
USE_EXTERNAL_UI: bool = True  # Toggle between external and in-process UI
```

When `True`, tools launch in a separate process. When `False`, legacy in-process mode is used.

### Configuration

The IPC server is automatically initialized when the first AYON tool is launched. It:

1. Starts a TCP server on `127.0.0.1` with an auto-selected port
2. Generates a session token for authentication
3. Launches the external UI process with connection details via environment variables
4. Registers handlers for all tool operations

### Registering Custom Handlers

Add handlers in `_register_ipc_handlers()`:

```python
def handle_custom_action(params: Dict) -> str:
    """Custom action handler."""
    def _do_action():
        # Do something in Blender main thread
        return "Success"
    
    mti = MainThreadItem(_do_action)
    execute_in_main_thread(mti)
    return mti.wait()

server.register_handler("custom_action", handle_custom_action)
```

### Publishing Events

From Blender, publish events to connected UI clients:

```python
server = _ipc_server_instance
if server:
    server.publish_event("custom_event", {
        "data": "some_value"
    })
```

Render events are automatically published:
- `render_started` - When Blender starts rendering
- `render_finished` - When rendering completes
- `render_cancelled` - When rendering is cancelled

### Subscribing to Events (from Qt process)

In the external UI process:

```python
from ayon_blender.api.ipc_client import IPCClient

ipc = IPCClient(host="127.0.0.1", port=9999, session_token="...")

def on_render_started(payload):
    print(f"Blender rendering: {payload.get('scene')}")

ipc.subscribe("render_started", on_render_started)
```

## Reconnection and Error Handling

### Automatic Reconnection

The IPC client implements exponential backoff:
- 1st attempt: 0.5s wait
- 2nd attempt: 1.0s wait
- 3rd attempt: 2.0s wait
- 4th+ attempts: 5.0s wait (capped)

### Blender Busy Detection

If Blender doesn't respond for 60+ seconds (e.g., during rendering), the client state changes to `BLENDER_BUSY`. The UI can show a "Blender is rendering..." message to the user.

Check state from Qt process:
```python
if ipc.is_blender_busy():
    show_busy_indicator()
```

### Graceful Degradation

- Requests include a `timeout_sec` parameter (default 30s)
- If timeout is exceeded, the callback is called with `ok=False, error="Request timeout"`
- UI should display appropriate feedback to user

## Per-Request Configuration

```python
ipc.send_request(
    method="show_tool",
    params={"tool": "creator"},
    timeout_sec=60.0,  # Request-specific timeout
    idempotency_key="ui-action-1",  # For deduplication
    callback=lambda ok, result, error: handle_response(ok, result, error)
)
```

## Render Awareness

Render event handlers in `ops.py` publish events:

```python
def _on_render_init(scene):
    """Called when Blender starts rendering."""
    if _ipc_server_instance:
        _ipc_server_instance.publish_event("render_started", {
            "scene": scene.name if scene else ""
        })
```

The Qt UI can listen for these and:
- Disable certain operations
- Show progress indicator
- Queue deferred actions

## Security

### Session Token

- Generated on server startup with `os.urandom(16).hex()`
- Passed to external process via environment variable
- Required for client to authenticate
- Should be kept private (passed only to trusted child process)

### Localhost Only

- Server binds to `127.0.0.1` only
- Cannot accept remote connections
- Safe within a single machine

## Logging

Both server and client use Python's standard `logging` module:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
```

Check logs to diagnose connection issues, timeouts, or request failures.

## Troubleshooting

### "Failed to connect" messages

1. Check Blender is running the addon
2. Verify `USE_EXTERNAL_UI = True` in `ops.py`
3. Check firewall allows `127.0.0.1` connections
4. Review debug logs for specific errors

### UI process crashes

1. Check stderr/stdout of external UI process
2. Verify all required dependencies (PySide2/PySide6) are installed
3. Check Blender compatibility (PySide version matters)

### Timeouts

1. Increase `timeout_sec` for long-running operations
2. Check if Blender is rendering (watch `BLENDER_BUSY` state)
3. Review Blender performance/profiling

### Stale connections

The client automatically detects and reconnects. If UI becomes unresponsive:
1. Close and reopen tool window
2. Restart Blender
3. Check for hung processes: `ps aux | grep python`

## Performance Considerations

### Benefits

- **No UI blocking**: Blender stays responsive during rendering
- **Parallel operation**: Tools can load/process while Blender works
- **Resource isolation**: Qt doesn't consume Blender's Python resources

### Overhead

- ~50-100ms for process startup (first time)
- ~1-5ms per RPC call (round-trip over socket)
- Extra memory for separate Python process (~100-200MB)

## Migration from In-Process

### Toggling Back to In-Process

Set `USE_EXTERNAL_UI = False` in `ops.py` to use legacy mode. Both modes coexist in the codebase.

### Operator Compatibility

Operators that work in both modes:
- `LaunchCreator`
- `LaunchLoader`
- `LaunchPublisher`
- `LaunchManager`
- `LaunchLibrary`
- `LaunchWorkFiles`

Custom operators inherit from `LaunchQtApp` and should work in both modes automatically.

## Future Improvements

- [ ] Window state persistence (size, position)
- [ ] Multi-window support per tool
- [ ] Streaming for large data transfers
- [ ] Binary protocol for better performance
- [ ] Encrypted socket support (TLS)
- [ ] Monitoring/statistics dashboard

