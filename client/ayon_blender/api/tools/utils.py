from pathlib import Path

from ayon_blender import BLENDER_ADDON_ROOT

SRIPT_PATH = (
    Path(BLENDER_ADDON_ROOT) / "ipc_communication" / "tools" / "ui_process.py"
)


def get_ui_process_script_path() -> Path:
    """Get UI process script path.

    Returns:
        str: Path to the UI process script.

    """
    return SRIPT_PATH


def show_message(title: str, message: str, level: str = "warning") -> None:
    # TODO implement
    print("DEV WARNING Missing implementation: 'show_message'")
    # from ayon_core.tools.utils import show_message_dialog
    # from .ops import BlenderApplication
    #
    # BlenderApplication.get_app()
    #
    # show_message_dialog(
    #     title=title,
    #     message=message,
    #     level="warning")
