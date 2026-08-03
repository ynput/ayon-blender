from __future__ import annotations

import typing

from ayon_core.tools.utils import show_message_dialog

from .utils import execute_in_main_thread

if typing.TYPE_CHECKING:
    from ayon_blender.ipc_communication.tools import CommunicationInfo
    from ayon_blender.ipc_communication import RequestMessage


class BlenderGenericFrontend:
    channel_name = "generic"

    def __init__(self, com_info: CommunicationInfo) -> None:
        com_info.register_channel_handler(
            self.channel_name, self._handle_request
        )
        self._com_info: CommunicationInfo = com_info

    def _handle_request(self, req: RequestMessage):
        if req.method == "show_message":
            execute_in_main_thread(self._show_message, **req.params)

    def _show_message(self, title: str, message: str, level: str) -> None:
        """Show a message in the UI."""
        show_message_dialog(
            title=title,
            message=message,
            level=level,
        )
