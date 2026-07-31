"""Run AYON Qt tools in an external process and control them via IPC events."""

import os
import sys
import logging
import time

import psutil

from ayon_blender.ipc_communication import IPCClient
from ayon_blender.ipc_communication.tools import (
    BlenderWorkfilesFrontend,
    BlenderLoaderFrontend,
    BlenderPublisherFrontend,
    start_main_thread_helper,
    execute_in_main_thread,
)

from ayon_core.tools.utils import get_ayon_qt_app

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Entry-point of the external UI process."""
    pid = int(os.environ["AYON_IPC_PID"])
    ipc_host = os.environ["AYON_IPC_HOST"]
    ipc_port = int(os.environ["AYON_IPC_PORT"])
    session_token = os.environ["AYON_IPC_TOKEN"]
    if not ipc_port or not session_token:
        logger.error("Missing IPC bootstrap env vars")
        sys.exit(1)

    app = get_ayon_qt_app()
    ipc = IPCClient(host=ipc_host, port=ipc_port, session_token=session_token)

    # Give Blender-side server a short startup window before hard failure.
    deadline = time.time() + 10.0
    while not ipc.connect() and time.time() < deadline:
        time.sleep(0.5)

    if not ipc.is_connected():
        logger.error("Could not connect to Blender IPC server")
        sys.exit(2)

    start_main_thread_helper()
    _workfiles = BlenderWorkfilesFrontend(ipc)
    _loader = BlenderLoaderFrontend(ipc)
    _publisher = BlenderPublisherFrontend(ipc)

    # Keep the process alive and attempt reconnection if Blender restarts.
    def _tick():
        if ipc.is_connected():
            execute_in_main_thread(_tick)
            return

        if psutil.pid_exists(pid):
            execute_in_main_thread(_tick)
            ipc.reconnect_with_backoff()
            return

        logger.error("Blender process has exited")
        if ipc.is_connected():
            ipc.disconnect()
        app.exit(0)

    execute_in_main_thread(_tick)

    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(ipc.disconnect)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
