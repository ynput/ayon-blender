from __future__ import annotations

import typing
from ayon_core.tools.workfiles.control import BaseWorkfileController

from ayon_blender.ipc_communication import IPCServer, RequestMessage


class BlenderWorkfilesController(BaseWorkfileController):
    channel_name = "workfiles"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def register_ipc_handler(self, ipc_server: IPCServer):
        ipc_server.register_handler(
            self.channel_name,
            self._channel_handler,
        )

    def _channel_handler(
        self, ipc_server: IPCServer, message: RequestMessage
    ):
        """Handle IPC messages for workfiles."""
        if message.method == "show":
            ipc_server.trigger_method(
                self.channel_name,
                "show",
            )
            return
        print(message)
