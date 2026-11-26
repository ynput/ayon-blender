from __future__ import annotations

import os
import re
import subprocess
from platform import system

from ayon_applications import LaunchTypes, PreLaunchHook
from ayon_core.lib import get_launcher_local_dir


# Blender's version folder is named after its version, e.g. "5.2". Some
# installations (and wrapper setups) use the full version, e.g. "5.2.2".
# Kept in one place so it is easy to adjust when Blender changes the naming.
VERSION_FOLDER_RE = re.compile(r"^(\d+)\.(\d+)(?:\.\d+)?$")


class InstallPySideToBlender(PreLaunchHook):
    """Install Qt bindings to 'application_packages' within AYON's local storage.

    Prelaunch hook does 5 things:
    1.) Blender's Python packages are pushed to the beginning of PYTHONPATH.
    2.) Check if Blender has installed Qt bindings. Return if found.
    3.) Check for application packages dir and add to PYTHONPATH.
    4.) Try to import Qt bindings from application packages. Return if found.
    4.) Install Qt bindings into application packages dir. Add to PYTHONPATH.

    For pipeline implementation is required to have Qt bindings available on PYTHONPATH.
    """

    app_groups = {"blender"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        # Prelaunch hook is not crucial
        if not self.data["project_settings"]["blender"]["hooks"].get(
                "install_pyside", True):
            self.log.debug("Skipping execution of %s.",
                           self.__class__.__name__)
            return
        try:
            self.inner_execute()
        except Exception:
            self.log.warning(
                "Processing of %s crashed.", self.__class__.__name__,
                exc_info=True,
            )

    def find_versions_dir(self, executable: str) -> str | None:
        """Find the directory that contains Blender's version folder.

        The configured application executable is not necessarily the Blender
        binary, it can be a wrapper script or a symlink. The version folder
        (e.g. '5.2') is detected by looking for a '<version>' folder with a
        'python' directory next to the executable, in its direct children and
        in its parent directories. The closest location wins, so a version
        folder of an unrelated application higher up in the tree can be
        picked up as a last resort.

        Args:
            executable (str): Path of the configured application executable.

        Returns:
            str | None: Directory containing Blender's version folder or None
                when no folder with Blender's python was found.
        """
        # Ordered candidates, closest location first.
        candidates = []
        executable_dir = os.path.dirname(executable)
        if system().lower() == "darwin":
            # On macOS the version folders live next to the executable folder
            # in "Contents/Resources".
            candidates.append(
                os.path.join(os.path.dirname(executable_dir), "Resources")
            )
        candidates.append(executable_dir)
        # Direct children of the executable's directory cover an installation
        # nested one level below a wrapper placed in the application root.
        # The directory is checked first because the executable path can be
        # empty or point to a folder that does not exist (e.g. a stale
        # application path), which would make the listing raise.
        if os.path.isdir(executable_dir):
            for entry in os.scandir(executable_dir):
                if entry.is_dir() and not VERSION_FOLDER_RE.match(entry.name):
                    candidates.append(entry.path)

        # The target of a symlink and the parent directories cover a wrapper
        # living inside the installation, e.g. "<install>/bin/blender". The
        # walk goes up to the filesystem root so no depth has to be guessed.
        for base in (
            executable_dir,
            os.path.dirname(os.path.realpath(executable)),
        ):
            current = os.path.abspath(base)
            while True:
                if current not in candidates:
                    candidates.append(current)
                parent = os.path.dirname(current)
                if parent == current:
                    break
                current = parent

        for candidate in candidates:
            if not os.path.isdir(candidate):
                continue
            for name in os.listdir(candidate):
                if VERSION_FOLDER_RE.match(name) and os.path.isdir(
                        os.path.join(candidate, name, "python")):
                    return candidate
        return None

    def inner_execute(self):
        platform = system().lower()
        executable = self.launch_context.executable.executable_path

        versions_dir = self.find_versions_dir(executable)
        if versions_dir is None:
            hint = (
                "\n"
                "[AYON] Blender was launched through '{}'\n"
                "       but Blender's install folder could not be found next"
                " to it or in its parent\n"
                "       directories (expected a '<version>' folder such as"
                " '5.2' containing 'python').\n"
                "       Blender's python packages are therefore not on"
                " PYTHONPATH and PySide6 is\n"
                "       not installed: the AYON menu will not load, and"
                " imports may fail with\n"
                "       \"ImportError: cannot import name 'NothingType'"
                " from 'attrs'\".\n"
                "       Fix: set the Blender application's \"Executable\" to"
                " the Blender binary\n"
                "       instead of a wrapper script, or place the wrapper"
                " inside the Blender\n"
                "       installation folder (e.g."
                " '<install>/bin/blender').\n"
            ).format(executable)
            self.log.warning(hint)
            return

        version_subfolders = [
            name for name in os.listdir(versions_dir)
            if VERSION_FOLDER_RE.match(name)
            and os.path.isdir(os.path.join(versions_dir, name, "python"))
        ]
        if len(version_subfolders) > 1:
            joined_subfolders = ", ".join([
                f'"./{name}"' for name in version_subfolders
            ])
            self.log.warning(
                "Found more than one version subfolder around the Blender"
                " executable. %s",
                joined_subfolders,
            )
            return

        version_subfolder = version_subfolders[0]
        before_blender_4 = False
        if int(VERSION_FOLDER_RE.match(version_subfolder).group(1)) < 4:
            before_blender_4 = True
        # Blender 4 has Python 3.11 which does not support 'PySide2'
        # QUESTION could we always install PySide6?
        qt_binding = "PySide2" if before_blender_4 else "PySide6"
        # Use PySide6 6.6.3 because 6.7.0 had a bug
        #   - 'QTextEdit' can't be added to 'QBoxLayout'
        qt_binding_version = None if before_blender_4 else "6.10.2"

        python_dir = os.path.join(versions_dir, version_subfolder, "python")
        python_lib = os.path.join(python_dir, "lib")
        python_version = "python"

        if platform != "windows":
            for dir_entry in os.scandir(python_lib):
                if dir_entry.is_dir() and dir_entry.name.startswith("python"):
                    python_lib = dir_entry.path
                    python_version = dir_entry.name
                    break

        # Get blender's python executable
        python_bin = os.path.join(python_dir, "bin")
        if platform == "windows":
            python_executable = os.path.join(python_bin, "python.exe")
        else:
            python_executable = os.path.join(python_bin, python_version)
            # Check for python with enabled 'pymalloc'
            if not os.path.exists(python_executable):
                python_executable += "m"

        if not os.path.exists(python_executable):
            self.log.warning(
                "Couldn't find python executable for blender. {}".format(
                    executable
                )
            )
            return

        # Check if application packages dir exists for Blender's Python version
        python_minor = self.get_python_version(python_executable)
        local_dir = get_launcher_local_dir()
        app_packages = os.path.join(
            local_dir, "application_packages", f"blender-py{python_minor}"
        )

        # Change PYTHONPATH to contain blender's packages as first
        python_paths = [
            python_lib,
            os.path.join(python_lib, "site-packages"),
        ]

        # Append application packages dir to Python path, if it exists
        if os.path.exists(app_packages):
            python_paths.append(app_packages)
        self.prepend_to_pythonpath(python_paths)

        # Check if Qt bindings are available
        if self.is_pyside_installed(python_executable, qt_binding):
            self.log.debug("Qt bindings are available.")
            return

        # Install PySide2 into application packages
        result = self.install_pyside(
            python_executable,
            qt_binding,
            qt_binding_version,
            app_packages,
        )
        if app_packages not in python_paths:
            self.prepend_to_pythonpath([app_packages])

        if result:
            self.log.info(
                "Successfully installed %s module to application packages.", qt_binding
            )
        else:
            self.log.warning(
                "Failed to install %s module to application packages.", qt_binding
            )

    def get_python_version(self, python_executable):
        """Return the major.minor version of given Python executable."""
        result = subprocess.run(
            [python_executable, "--version"],
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip() or result.stderr.strip()
        match = re.search(r"(\d+\.\d+)", output)
        if not match:
            raise RuntimeError(
                f"Could not parse Python version from: {output!r}"
            )

        version = match.group(1)
        self.log.debug(f"Blender Python version: {version}")
        return version

    def prepend_to_pythonpath(self, paths: list[str]):
        """Prepend given paths to PYTHONPATH"""
        python_path = self.launch_context.env.get("PYTHONPATH") or ""
        for path in python_path.split(os.pathsep):
            if path:
                paths.append(path)

        self.launch_context.env["PYTHONPATH"] = os.pathsep.join(paths)

    def install_pyside(
        self,
        python_executable,
        qt_binding,
        qt_binding_version,
        target,
    ):
        """Install Qt binding python module to blender's python."""
        if qt_binding_version:
            qt_binding = f"{qt_binding}=={qt_binding_version}"
        try:
            # Parameters
            # - use "-m pip" as module pip to install qt binding and argument
            #   "--ignore-installed" is to force install module to blender's
            #   site-packages and make sure it is binary compatible
            # TODO find out if blender 4.x on linux/darwin does install
            #   qt binding to correct place.
            args = [
                python_executable,
                "-m",
                "pip",
                "install",
                "--ignore-installed",
                "--target",
                target,
                qt_binding,
            ]
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, universal_newlines=True
            )
            process.communicate()
            return process.returncode == 0
        except PermissionError:
            self.log.warning(
                'Permission denied with command: "%s".', " ".join(args)
            )
        except OSError as error:
            self.log.warning('OS error has occurred: "%s".', error)
        except subprocess.SubprocessError:
            pass

    def is_pyside_installed(self, python_executable, qt_binding):
        """Check if there is a Qt Binding that is importable with blender python."""
        args = [
            python_executable,
            "-c",
            f"import {qt_binding}",
        ]
        kwargs = {}
        if system().lower() == "windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        returncode = subprocess.call(
            args,
            env=self.launch_context.env,
            text=True,
            **kwargs,
        )
        if returncode == 0:
            self.log.debug(
                "%s imported with blender's python.", qt_binding
            )
            return True
        self.log.warning(
            "Could not import %s, will attempt to install it.",
            qt_binding,
        )
        return False
