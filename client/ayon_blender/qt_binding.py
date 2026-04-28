import bpy
import importlib
import os
from pathlib import Path

from . import venvman


PYSIDE6_VERSION: str = "6.10.2"


def ensure_qt_binding():
    """
    Provide Qt binding via virtual environment, if necessary.
    """

    def check_import(qt_binding: str) -> bool:
        """
        Check if given Qt library is available.

        Args:
            qt_binding (str): Library to check

        Returns:
            bool: True if the import is successful
        """
        try:
            importlib.import_module(qt_binding)
            return True
        except ImportError:
            return False

    # Use PySide2 for Blender versions before 4.0
    if bpy.app.version[0] < 4:
        qt_binding = "PySide2"
        version = None
    else:
        qt_binding = "PySide6"
        version = PYSIDE6_VERSION

    # Try importing any compatible Qt library from package libraries
    print(f"Attempting {qt_binding} import from package libraries...")
    if check_import(qt_binding):
        print(f"Qt binding {qt_binding} available in package libraries.")
        return

    # Prepare the virtual environment
    venv_path = Path(
        os.environ.get("AYON_LAUNCHER_LOCAL_DIR", ""),
        "virtualenvs",
        f"blender-{bpy.app.version_string}",
    )
    vman = venvman.VenvManager(venv_path, verbose=True)
    vman.initialize()

    # Check if the virtual environment already contains a Qt package
    print(f"Attempting {qt_binding} import from virtual environment...")
    if check_import(qt_binding):
        print(f"Qt binding {qt_binding} available in virtual environment.")
        return

    # Install PySide6 into the virtual environment
    vman.install_package(qt_binding, version)
    if not check_import(qt_binding):
        raise RuntimeError("Unable to ensure Qt binding for Blender.")


# Run immediately on import
ensure_qt_binding()
