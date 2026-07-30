from __future__ import annotations

from ayon_core.tools.workfiles.control import BaseWorkfileController

from ayon_blender.ipc_communication import IPCServer, RequestMessage


class BlenderWorkfilesController(BaseWorkfileController):
    channel_name = "workfiles"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._ipc_server: IPCServer | None = None

    def register_ipc_handler(self, ipc_server: IPCServer):
        self._ipc_server = ipc_server
        ipc_server.register_handler(
            self.channel_name,
            self._channel_handler,
        )

    # --- Custom handling of events ---
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self.event_system.emit(topic, data, source)
        if self._ipc_server is not None:
            self._ipc_server.trigger_method(
                self.channel_name,
                "emit_event",
                {"topic": topic, "data": data, "source": source},
            )

    def _channel_handler(
        self, ipc_server: IPCServer, message: RequestMessage
    ):
        """Handle IPC messages for workfiles."""
        method_name = message.method
        if message.method == "show":
            ipc_server.trigger_method(
                self.channel_name,
                "show",
            )
            return None

        func = getattr(self, method_name)
        return func(**message.params)

