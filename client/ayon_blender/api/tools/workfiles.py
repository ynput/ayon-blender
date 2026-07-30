from __future__ import annotations

from typing import Any

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
        output = func(**message.params)

        if method_name == "get_folder_items":
            return {
                entity_id: item.to_data()
                for entity_id, item in output.items()
            }

        if method_name in (
            "get_task_items",
            "get_folder_type_items",
            "get_task_type_items",
            "get_published_file_items",
            "get_workarea_file_items",
        ):
            return [item.to_data() for item in output]

        if method_name == "fill_workarea_filepath":
            return {
                "root": output.root,
                "filename": output.filename,
                "exists": output.exists,
                "filepath": output.filepath,
            }

        if method_name == "get_published_workfile_info":
            return {
                "info": output.info,
                "comment": output.comment,
            }

        if method_name == "get_user_items_by_name":
            return {
                username: dict(
                    username=user_item.username,
                    full_name=user_item.full_name,
                    email=user_item.email,
                    avatar_url=user_item.avatar_url,
                    active=user_item.active,
                )
                for username, user_item in output.items()
            }

        if method_name == "get_workfile_info":
            if output is None:
                return None
            return output.to_data()

        return output