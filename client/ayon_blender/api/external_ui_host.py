"""Run AYON Qt tools in an external process and control them via IPC events."""

import os
import subprocess
import sys
import logging
from pathlib import Path

from qtpy import QtCore, QtWidgets

from ayon_core.lib import get_ayon_launcher_args

from ayon_blender.ipc_communication import (
    IPCClient,
    RemoteLoaderFrontendController,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_external_ui_process_launcher():
    """Create a callable that launches the external Qt host process."""
    launcher_script = Path(__file__).resolve()

    def launch_ui_process(ipc_host: str, ipc_port: int, session_token: str) -> subprocess.Popen:
        env = os.environ.copy()
        env["AYON_IPC_HOST"] = ipc_host
        env["AYON_IPC_PORT"] = str(ipc_port)
        env["AYON_IPC_TOKEN"] = session_token
        return subprocess.Popen(
            get_ayon_launcher_args("run", str(launcher_script)),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return launch_ui_process


def _show_tool(tool_name, tab=None):
    from ayon_core.tools.utils import host_tools

    if tool_name == "publisher":
        host_tools.show_publisher(tab=tab or "publish")
        return

    window = host_tools.get_tool_by_name(tool_name)
    if hasattr(window, "show"):
        window.show()
    if tab and hasattr(window, "set_current_tab"):
        window.set_current_tab(tab)
    if hasattr(window, "raise_"):
        window.raise_()
    if hasattr(window, "activateWindow"):
        window.activateWindow()


def _show_loader_window(loader_window_by_name, loader_controller_by_name, ipc_client, tool_name):
    from ayon_core.tools.loader.ui import LoaderWindow

    controller = loader_controller_by_name.get(tool_name)
    window = loader_window_by_name.get(tool_name)
    if controller is None:
        controller = RemoteLoaderFrontendController(ipc_client)
        loader_controller_by_name[tool_name] = controller

    if window is None:
        window = LoaderWindow(controller=controller)
        loader_window_by_name[tool_name] = window

    window.show()
    window.raise_()
    window.activateWindow()
    window.showNormal()
    window.refresh()


def main():
    """Entry-point of the external UI process."""
    ipc_host = os.environ.get("AYON_IPC_HOST", "127.0.0.1")
    ipc_port = int(os.environ.get("AYON_IPC_PORT", "0"))
    session_token = os.environ.get("AYON_IPC_TOKEN", "")

    if not ipc_port or not session_token:
        logger.error("Missing IPC bootstrap env vars")
        sys.exit(1)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    ipc = IPCClient(host=ipc_host, port=ipc_port, session_token=session_token)
    loader_window_by_name = {}
    loader_controller_by_name = {}

    if not ipc.connect():
        logger.error("Could not connect to Blender IPC server")
        sys.exit(2)

    def on_open_tool(payload):
        tool_name = payload.get("tool")
        tab = payload.get("tab")
        try:
            if tool_name in {"loader", "libraryloader"}:
                _show_loader_window(
                    loader_window_by_name,
                    loader_controller_by_name,
                    ipc,
                    tool_name,
                )
            else:
                _show_tool(tool_name, tab)
        except Exception:
            logger.exception("Failed to open tool '%s'", tool_name)

    ipc.subscribe("open_tool", on_open_tool)

    # Keep the process alive and attempt reconnection if Blender restarts.
    def _tick():
        for controller in list(loader_controller_by_name.values()):
            controller.process_events()

        if not ipc.is_connected():
            ipc.reconnect_with_backoff()

    timer = QtCore.QTimer()
    timer.timeout.connect(_tick)
    timer.start(1000)

    app.aboutToQuit.connect(ipc.disconnect)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()



