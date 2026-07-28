"""Loader controller bridge between Blender and an external Qt process."""

from __future__ import annotations

import base64
import collections
import importlib
import pickle
from typing import Any, Callable, Optional


def serialize_for_ipc(value: Any) -> Any:
    """Convert Python values to JSON-safe payload.

    The bridge prefers explicit model serialization (`to_data`) and falls back
    to pickle for objects that are not natively serializable.
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, list):
        return [serialize_for_ipc(item) for item in value]

    if isinstance(value, tuple):
        return {
            "__type__": "tuple",
            "items": [serialize_for_ipc(item) for item in value],
        }

    if isinstance(value, set):
        return {
            "__type__": "set",
            "items": [serialize_for_ipc(item) for item in value],
        }

    if isinstance(value, dict):
        return {
            str(key): serialize_for_ipc(item)
            for key, item in value.items()
        }

    if hasattr(value, "to_data") and callable(value.to_data):
        class_path = f"{value.__class__.__module__}:{value.__class__.__name__}"
        return {
            "__type__": "ayon_model",
            "class": class_path,
            "data": serialize_for_ipc(value.to_data()),
        }

    raw = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    return {
        "__type__": "pickle",
        "data": base64.b64encode(raw).decode("ascii"),
    }


def deserialize_from_ipc(value: Any) -> Any:
    """Restore Python values encoded with `serialize_for_ipc`."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, list):
        return [deserialize_from_ipc(item) for item in value]

    if isinstance(value, dict):
        value_type = value.get("__type__")
        if value_type == "tuple":
            return tuple(deserialize_from_ipc(item) for item in value["items"])

        if value_type == "set":
            return set(deserialize_from_ipc(item) for item in value["items"])

        if value_type == "ayon_model":
            class_path = value["class"]
            module_name, class_name = class_path.split(":", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            data = deserialize_from_ipc(value["data"])
            if hasattr(cls, "from_data") and callable(cls.from_data):
                return cls.from_data(data)
            return cls(**data)

        if value_type == "pickle":
            raw = base64.b64decode(value["data"].encode("ascii"))
            return pickle.loads(raw)

        return {
            key: deserialize_from_ipc(item)
            for key, item in value.items()
        }

    return value


class _EventProxy:
    """Tiny event object compatible with AYON event callbacks in UI widgets."""

    def __init__(self, event_data: dict[str, Any]):
        self._topic = event_data.get("topic")
        self._source = event_data.get("source")
        self._data = event_data.get("data") or {}

    @property
    def topic(self):
        return self._topic

    @property
    def source(self):
        return self._source

    @property
    def data(self):
        return self._data

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, *args, **kwargs):
        return self._data.get(key, *args, **kwargs)


class BlenderLoaderBackendBridge:
    """Backend-side bridge: keeps `LoaderController` inside Blender process."""

    def __init__(self, ipc_server):
        from ayon_core.pipeline import registered_host
        from ayon_core.tools.loader import LoaderController

        self._ipc_server = ipc_server
        self._controller = LoaderController(host=registered_host())
        self._event_callback = self._controller.register_event_callback(
            "*", self._on_controller_event
        )

    def _on_controller_event(self, event):
        self._ipc_server.publish_event(
            "loader_event",
            {
                "event": serialize_for_ipc(event.to_data()),
            }
        )

    def call_method(self, method_name: str, args: Optional[list], kwargs: Optional[dict]):
        args = args or []
        kwargs = kwargs or {}
        method = getattr(self._controller, method_name)
        return method(*args, **kwargs)


class RemoteLoaderFrontendController:
    """Frontend-side proxy that forwards LoaderController calls over IPC."""

    def __init__(self, ipc_client):
        self._ipc_client = ipc_client
        self._event_callbacks: dict[str, list[Callable]] = collections.defaultdict(list)
        self._pending_events = collections.deque()
        self._ipc_client.subscribe("loader_event", self._on_loader_event)

    def _on_loader_event(self, payload: dict[str, Any]):
        event_data = deserialize_from_ipc(payload.get("event"))
        if event_data:
            self._pending_events.append(event_data)

    def process_events(self):
        while self._pending_events:
            event_data = self._pending_events.popleft()
            event = _EventProxy(event_data)
            callbacks = list(self._event_callbacks.get(event.topic) or [])
            callbacks.extend(self._event_callbacks.get("*") or [])
            for callback in callbacks:
                callback(event)

    def register_event_callback(self, topic, callback):
        self._event_callbacks[topic].append(callback)

    def _remote_call(self, method_name, *args, **kwargs):
        ok, result, error = self._ipc_client.send_request_wait(
            "loader_call",
            {
                "method": method_name,
                "args": serialize_for_ipc(list(args)),
                "kwargs": serialize_for_ipc(kwargs),
            },
            timeout_sec=180.0,
        )
        if not ok:
            raise RuntimeError(error or f"Remote loader call failed: {method_name}")
        return deserialize_from_ipc(result)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def caller(*args, **kwargs):
            return self._remote_call(name, *args, **kwargs)

        return caller

