from __future__ import annotations

from ayon_core.tools.loader.control import LoaderController

from ayon_blender.ipc_communication import IPCServer, RequestMessage
from ayon_blender.api.execution import execute_in_main_thread

try:
    from ayon_core.lib import IconBase
except ImportError:
    IconBase = type("IconBase", (), {})


class BlenderLoaderBackend(LoaderController):
    channel_name = "loader"

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

    def _emit_event(self, topic, data=None):
        self.emit_event(topic, data or {}, "controller")

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
        if method_name in (
            "trigger_action_item",
        ):
            execute_in_main_thread(func, **message.params)
            return None

        output = func(**message.params)
        if output is None:
            return output


        if method_name == "get_product_type_items":
            items = [item.to_data() for item in output]
            if not items:
                return []

            if isinstance(items[0]["icon"], IconBase):
                for item in items:
                    item["icon"] = item["icon"].to_data()
            return items

        if method_name in (
            "get_project_items",
            "get_task_items",
            "get_folder_type_items",
            "get_task_type_items",
            "get_project_status_items",
            "get_product_items",
            "get_representation_items",
            "get_action_items",
        ):
            return [item.to_data() for item in output]

        if method_name == "get_product_item":
            return output.to_data()

        if method_name == "get_project_anatomy_tags":
            return [
                {"name": item.name, "color": item.color}
                for item in output
            ]

        if method_name == "get_product_type_icons_mapping":
            return {
                "default": output._default,
                "definitions": output._definitions,
            }

        # Values in the dictionary are sets, which are not JSON serializable.
        if method_name == "get_my_tasks_entity_ids":
            return {
                "entity_ids": list(output["entity_ids"]),
                "assignees": list(output["assignees"]),
            }

        if method_name == "get_product_types_filter":
            return {
                "product_types": output.product_types,
                "is_allow_list": output.is_allow_list,
            }

        # set -> list conversion
        if method_name in (
            "get_selected_folder_ids",
            "get_selected_task_ids",
            "get_selected_version_ids",
            "get_selected_representation_ids",
            "get_loaded_product_ids",
        ):
            return list(output)

        if method_name in (
            "get_active_site_icon_def",
            "get_remote_site_icon_def",
        ):
            if isinstance(output, IconBase):
                return output.to_data()
            return output

        return output
