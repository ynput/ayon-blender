import os
import re
import subprocess
from platform import system

from ayon_applications import LaunchTypes, PreLaunchHook
from ayon_core.lib import get_launcher_local_dir


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

    def inner_execute(self):
        # Get blender's python directory
        version_regex = re.compile(r"^([2-5])\.[0-9]+$")

        platform = system().lower()
        executable = self.launch_context.executable.executable_path
        expected_executable = "blender"
        if platform == "windows":
            expected_executable += ".exe"

        if os.path.basename(executable).lower() != expected_executable:
            self.log.info(
                "Executable does not lead to %s file."
                "Can't determine blender's python to check/install"
                " Qt binding.",
                expected_executable,
            )
            return

        versions_dir = os.path.dirname(executable)
        if platform == "darwin":
            versions_dir = os.path.join(
                os.path.dirname(versions_dir), "Resources"
            )
        version_subfolders = []
        for dir_entry in os.scandir(versions_dir):
            if dir_entry.is_dir() and version_regex.match(dir_entry.name):
                version_subfolders.append(dir_entry.name)

        if not version_subfolders:
            self.log.info(
                "Didn't find version subfolder next to Blender executable"
            )
            return

        if len(version_subfolders) > 1:
            joined_subfolders = ", ".join([
                f'"./{name}"' for name in version_subfolders
            ])
            self.log.info(
                "Found more than one version subfolder next"
                " to blender executable. %s",
                joined_subfolders
            )
            return

        version_subfolder = version_subfolders[0]
        before_blender_4 = False
        if int(version_regex.match(version_subfolder).group(1)) < 4:
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
