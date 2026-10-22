from __future__ import annotations

import os
import re
import subprocess
from platform import system

from ayon_applications import LaunchTypes, PreLaunchHook


# Blender's version folder is named after its version, e.g. "5.2". Some
# installations (and wrapper setups) use the full version, e.g. "5.2.2".
# Kept in one place so it is easy to adjust when Blender changes the naming.
VERSION_FOLDER_RE = re.compile(r"^(\d+)\.(\d+)(?:\.\d+)?$")


class InstallPySideToBlender(PreLaunchHook):
    """Install Qt binding to blender's python packages.

    Prelaunch hook does 2 things:
    1.) Blender's python packages are pushed to the beginning of PYTHONPATH.
    2.) Check if blender has installed PySide2 and will try to install if not.

    For pipeline implementation is required to have Qt binding installed in
    blender's python packages.
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
            self.log.warning(
                "Could not find Blender's install folder (a '<version>' folder"
                " containing 'python') around '%s'. Point the application at"
                " the Blender binary instead of the wrapper, or place the"
                " wrapper inside the Blender installation folder (e.g."
                " '<install>/bin/blender').",
                executable,
            )
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

        # Change PYTHONPATH to contain blender's packages as first
        python_paths = [
            python_lib,
            os.path.join(python_lib, "site-packages"),
        ]
        python_path = self.launch_context.env.get("PYTHONPATH") or ""
        for path in python_path.split(os.pathsep):
            if path:
                python_paths.append(path)

        self.launch_context.env["PYTHONPATH"] = os.pathsep.join(python_paths)

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

        # Check if PySide2 is installed and skip if yes
        if self.is_pyside_installed(python_executable, qt_binding):
            self.log.debug("Blender has already installed PySide2.")
            return

        # Install PySide2 in blender's python
        if platform == "windows":
            result = self.install_pyside_windows(
                python_executable,
                qt_binding,
                qt_binding_version,
                before_blender_4,
            )
        else:
            result = self.install_pyside(
                python_executable,
                qt_binding,
                qt_binding_version,
            )

        if result:
            self.log.info(
                "Successfully installed %s module to blender.", qt_binding
            )
        else:
            self.log.warning(
                "Failed to install %s module to blender.", qt_binding
            )

    def install_pyside_windows(
        self,
        python_executable,
        qt_binding,
        qt_binding_version,
        before_blender_4,
    ):
        """Install PySide2 python module to blender's python.

        Installation requires administration rights that's why it is required
        to use "pywin32" module which can execute command's and ask for
        administration rights.
        """
        try:
            import pywintypes
            import win32con
            import win32event
            import win32process
            from win32comext.shell import shellcon
            from win32comext.shell.shell import ShellExecuteEx
        except Exception:
            self.log.warning('Couldn\'t import "pywin32" modules')
            return

        if qt_binding_version:
            qt_binding = f"{qt_binding}=={qt_binding_version}"

        try:
            # Parameters
            # - use "-m pip" as module pip to install PySide2 and argument
            #   "--ignore-installed" is to force install module to blender's
            #   site-packages and make sure it is binary compatible
            fake_exe = "fake.exe"
            site_packages_prefix = os.path.dirname(
                os.path.dirname(python_executable)
            )
            args = [
                fake_exe,
                "-m",
                "pip",
                "install",
                "--ignore-installed",
                qt_binding,
            ]
            if not before_blender_4:
                # Define prefix for site package
                # Python in blender 4.x is installing packages in AppData and
                #   not in blender's directory.
                args.extend(["--prefix", site_packages_prefix])

            parameters = (
                subprocess.list2cmdline(args)
                .removeprefix(fake_exe)
                .lstrip(" ")
            )

            # Execute command and ask for administrator's rights
            process_info = ShellExecuteEx(
                nShow=win32con.SW_SHOWNORMAL,
                fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
                lpVerb="runas",
                lpFile=python_executable,
                lpParameters=parameters,
                lpDirectory=os.path.dirname(python_executable),
            )
            process_handle = process_info["hProcess"]
            win32event.WaitForSingleObject(process_handle, win32event.INFINITE)
            returncode = win32process.GetExitCodeProcess(process_handle)
            return returncode == 0
        except pywintypes.error:
            pass

    def install_pyside(
        self,
        python_executable,
        qt_binding,
        qt_binding_version,
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
