from __future__ import annotations

from ayon_core.tools.publisher.control import PublisherController

from ayon_blender.ipc_communication import IPCServer, RequestMessage
from ayon_blender.api.execution import execute_in_main_thread


class BlenderPublisherBackend(PublisherController):
    channel_name = "publisher"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._ipc_server: IPCServer | None = None

    def register_ipc_handler(self, ipc_server: IPCServer):
        self._ipc_server = ipc_server
        ipc_server.register_handler(
            self.channel_name,
            self._channel_handler,
        )

    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        super().emit_event(topic, data, source)

        new_data = {}
        for key, value in data.items():
            if isinstance(value, set):
                value = list(value)
            new_data[key] = value

        self._ipc_server.trigger_method(
            self.channel_name,
            "emit_event",
            {"topic": topic, "data": new_data, "source": source},
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
                message.params,
            )
            return None

        func = getattr(self, method_name)
        if method_name in (
            "set_instances_context_info",
            "set_instances_active_state",
            "set_instances_create_attr_values",
            "revert_instances_create_attr_values",
            "set_instances_publish_attr_values",
            "revert_instances_publish_attr_values",
            "trigger_pre_create_button_callback",
            "trigger_create_button_callback",
            "trigger_publish_button_callback",
            "create",
            "trigger_convertor_items",
            "remove_instances",
            "save_changes",
            "publish",
            "validate",
            "stop_publish",
            "run_action",
        ):
            execute_in_main_thread(func, **message.params)
            return None

        return func(**message.params)
