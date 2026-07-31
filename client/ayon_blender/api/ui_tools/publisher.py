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

        self._ipc_server.trigger_method(
            self.channel_name,
            "emit_event",
            {"topic": topic, "data": data, "source": source},
        )

        super().emit_event(topic, data, source)

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
            "save_changes",
            "create",
            "trigger_convertor_items",
        ):
            item = execute_in_main_thread(func, **message.params)
            item.wait()
            return item.result

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
            "remove_instances",
            "publish",
            "validate",
            "stop_publish",
            "run_action",
        ):
            execute_in_main_thread(func, **message.params)
            return None

        return func(**message.params)

    def _start_publish(self, up_validation):
        self._publish_model.set_publish_up_validation(up_validation)
        self._publish_model.start_publish(wait=False)
        execute_in_main_thread(self._next_process)

    def _next_process(self):
        if self._publish_model.is_running():
            func = self._publish_model.get_next_process_func()
            func()
            execute_in_main_thread(self._next_process)
