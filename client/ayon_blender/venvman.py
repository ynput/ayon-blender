from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from io import BytesIO
    from types import SimpleNamespace

import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.parse import urlparse
from urllib.request import urlretrieve
from venv import EnvBuilder


class VenvManager(EnvBuilder):
    """
    Manage a virtual environment for the current Python interpreter.
    """

    env_dir: Path
    requirements_file: Path | None
    verbose: bool

    @property
    def pip_path(self) -> Path:
        return self.env_dir / "bin" / "pip"

    @property
    def python_path(self) -> Path:
        return self.env_dir / "bin" / "python"

    def __init__(
        self,
        venv_path: Path | str,
        requirements_file: Path | None = None,
        verbose: bool = False,
    ):
        """
        Create a virtual environment manager.

        Args:
            venv_path (Path | str): Path to the virtual environment
            requirements_file (Path | None): Path to the requirements.txt
            verbose (bool): Print verbose output
        """
        self.env_dir = Path(venv_path)
        self.requirements_file = requirements_file
        self.verbose = verbose

        super().__init__(
            system_site_packages=False,
            clear=False,
            symlinks=False,
            upgrade=False,
            with_pip=True,
            prompt=None,
            upgrade_deps=False,
        )

    def add_to_path(self, prepend: bool = False):
        """
        Ensure the virtual environment's site-packages is in the path.

        Args:
            prepend (bool): Ensure first position
        """
        context = self.ensure_directories(self.env_dir)
        if hasattr(context, "lib_path"):
            lib_path = context.lib_path
        else:
            major = sys.version_info.major
            minor = sys.version_info.minor
            lib_path = (
                f"{context.env_dir}/lib/python{major}.{minor}/site-packages"
            )

        # Check if already in path and in first position
        try:
            index = sys.path.index(lib_path)
            if not prepend or index == 0:
                self.print(f"{lib_path} already in PYTHONPATH.")
                return
            self.print(f"Moving {lib_path} to first position.")
            sys.path.pop(index)
        except ValueError:
            self.print(f"Adding {lib_path} to PYTHONPATH.")

        # Add to path
        if prepend:
            sys.path.insert(0, lib_path)
        else:
            sys.path.append(lib_path)

    def initialize(self) -> Path:
        """
        Check the virtual environment. (Re-)reate it if necessary.
        Add the virtual environment's site-packages to the path.

        Returns:
            Path: Path to the virtual environment
        """
        context = self.ensure_directories(self.env_dir)

        self.print(f"Checking virtual environment at {self.env_dir}.")

        # Check if the virtual environment exists and is complete
        executable_path = Path(context.executable).resolve()
        env_exe_path = Path(context.env_exe).resolve()
        sys_executable_path = Path(sys.executable).resolve()

        is_valid_exe = False
        if (
            executable_path.exists()
            and env_exe_path.exists()
            and (
                sys_executable_path == executable_path
                or sys_executable_path == env_exe_path
            )
            and self.pip_path.exists()
        ):
            # Call the executable and check its return code
            try:
                check_args = (
                    env_exe_path, "-c", "import sys; print(sys.executable)"
                )
                subprocess.check_call(check_args)
                is_valid_exe = True
            except subprocess.CalledProcessError:
                self.print("Non-zero return code from python executable.")

        if is_valid_exe:
            self.print("Virtual environment verified.")

        else:
            # If the virtual environment exists but is invalid recreate it
            if self.env_dir.exists():
                self.print("Virtual environment exists, but is invalid.")

            # Create the virtual environment
            self.print("Creating virtual environment.")
            self.create(self.env_dir)

        self.add_to_path(prepend=True)
        os.environ["VIRTUAL_ENV"] = str(self.env_dir)

        return self.env_dir

    def install_package(self, package: str, version: str | None = None):
        """
        Install a package in the virtual environment.

        Args:
            package (str): Package name
            version (str | None): Package version
        """
        if version:
            package = f"{package}=={version}"
        self.print(f"Installing {package} using pip.")
        subprocess.check_call((self.pip_path, "install", package))

    def install_pip(self):
        """
        Install pip in the virtual environment.
        """
        self.print("Installing pip.")
        url = "https://bootstrap.pypa.io/get-pip.py"
        self.install_script("pip", url)

    def install_requirements(self) -> list[str] | None:
        """
        Install add-on requirements.

        Returns:
            list[str] | None: List of installed packages if successful
        """
        if not self.requirements_file:
            self.print("No requirements file specified.")
            return

        self.print("Checking/installing dependencies using pip.")

        # Use pip freeze in a sub process to extract all installed modules
        freeze = subprocess.run(
            (self.pip_path, "freeze"),
            capture_output=True,
            text=True,
        ).stdout

        # Compare requirements with list of installed packages
        installed_packages = []
        with open(self.requirements_file) as req_file:
            packages = req_file.readlines()
            for line in packages:
                package = line.replace("\n", "")
                if package in freeze:
                    self.print(f"Dependency {package} satisfied.")
                    continue

                # If requirement not found in installed packages, install it
                self.print(f"Installing {package}")
                subprocess.check_call((self.pip_path, "install", package))
                installed_packages.append(package)

        return installed_packages

    def install_script(self, name: str, url: str):
        """
        Install a script in the virtual environment.

        Args:
            name (str): Script name
            url (str): Script URL
        """
        context = self.ensure_directories(self.env_dir)
        _, _, path, _, _, _ = urlparse(url)
        fn = Path(path).name
        bin_path = Path(context.bin_path)
        dist_path = bin_path / fn

        # Download script into the virtual environment's binaries folder
        print(f"Downloading {name} from {url} to {dist_path}")
        urlretrieve(url, dist_path)

        # Install in the virtual environment
        proc = subprocess.Popen(
            (context.env_exe, fn),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(bin_path),
        )

        thread_out = Thread(target=self.reader, args=(proc.stdout,))
        thread_out.start()
        thread_err = Thread(target=self.reader, args=(proc.stderr,))
        thread_err.start()
        proc.wait()
        thread_out.join()
        thread_err.join()

        # Clean up
        dist_path.unlink()

        if proc.returncode != 0:
            raise Exception(f"Failed to install script {name}")

    def freeze_requirements(self):
        """
        Create or update requirements.txt current package versions.
        """
        if not self.requirements_file:
            self.print("No requirements file specified.")
            return

        # Use pip freeze in a sub process to extract all installed modules
        freeze = subprocess.run(
            (self.pip_path, "freeze"),
            capture_output=True,
            text=True,
        ).stdout
        freeze_packages = freeze.split("\n")

        # Read the current requirements and build a list of package names
        with open(self.requirements_file, "r") as req_file:
            req_lines = req_file.readlines()
            packages = [line.split("==")[0] for line in req_lines if line]

        # Write all existing frozen packages back into requirements
        self.print("Re-write only relevant package versions.")
        with open(self.requirements_file, "w") as req_file:
            for freeze_package in freeze_packages:
                package = freeze_package.split("==")[0]

                # Skip empty lines
                if not package or package == "\n" or package not in packages:
                    continue

                # Write the frozen package with version into requirements file
                self.print(f"Writing {package}")
                req_file.write(freeze_package + "\n")

    def post_setup(self, context: SimpleNamespace):
        """
        Install setuptools and pip in the virtual environment.

        Args:
            context (SimpleNamespace): Virtual environment information
        """
        os.environ["VIRTUAL_ENV"] = context.env_dir
        try:
            # Check if pip is installed
            import pip  # noqa: F401
        except ImportError:
            self.install_pip()

        # self.install_setuptools()

    def print(self, message: str):
        """
        Print information if verbose mode is enabled.

        Args:
            message (str): Message to print
        """
        if self.verbose:
            print(message)

    def reader(self, stream: BytesIO):
        """
        Read lines from a subprocess' output stream.
        Pass it to a progress callable (if specified) or write progress
        information to sys.stderr.

        Args:
            stream (BytesIO): A stream object from which to read
        """
        while True:
            line = stream.readline()
            if not line:
                break
            if self.verbose:
                sys.stderr.write(line.decode("utf-8"))
            else:
                sys.stderr.write(".")
            sys.stderr.flush()
        stream.close()

    def update_requirements(self) -> list[str] | None:
        """
        Update packages listed in requirements.txt to the newest version.

        Returns:
            list[str] | None: List of updated packages if successful
        """
        if not self.requirements_file:
            self.print("No requirements file specified.")
            return

        self.print("Updating dependencies using pip.")

        # Read requirements file line by line
        updated_packages = []
        with open(self.requirements_file) as req_file:
            req_lines = req_file.readlines()
            for line in req_lines:
                # Remove version number to enforce latest release
                package = line.split("==")[0]

                # Skip empty lines
                if not package or package == "\n":
                    continue

                # Install latest release; throws and error which we ignore
                subprocess.run(
                    (self.pip_path, "install", package, "--upgrade"),
                    check=False,
                )
                updated_packages.append(package)

                # Display/print package information to indicate success
                subprocess.check_call((self.pip_path, "show", package))

        return updated_packages

    def upgrade_package(self, package: str):
        """
        Upgrade a package in the virtual environment.

        Args:
            package (str): Package name
        """
        self.print(f"Upgrading {package} using pip.")
        subprocess.check_call((self.pip_path, "install", "--upgrade", package))
