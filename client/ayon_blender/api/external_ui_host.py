"""Run AYON Qt tools in an external process and control them via IPC events."""

import os
import sys
import logging
import time

from qtpy import QtCore

from ayon_blender.ipc_communication import IPCClient
from ayon_blender.ipc_communication.tools import BlenderWorkfilesFrontend

from ayon_core.tools.utils import get_ayon_qt_app


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Entry-point of the external UI process."""
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

    workfiles = BlenderWorkfilesFrontend(ipc)

    # Keep the process alive and attempt reconnection if Blender restarts.
    def _tick():
        if not ipc.is_connected():
            ipc.reconnect_with_backoff()

    timer = QtCore.QTimer()
    timer.timeout.connect(_tick)
    timer.start(1000)

    app.aboutToQuit.connect(ipc.disconnect)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()



