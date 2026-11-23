from ayon_applications import PreLaunchHook


class AddPythonUseSystemEnvArg(PreLaunchHook):
    """Add `--python-use-system-env` to Blender launch arguments.

    Without this argument Blender ignores the process environment, including
    `PYTHONPATH`, and the AYON integration fails to import.
    """

    app_groups = {"blender"}
    launch_types = set()  # Empty set means all launch types

    argument = "--python-use-system-env"

    def execute(self):
        hooks_settings = self.data["project_settings"]["blender"]["hooks"]
        if not hooks_settings.get("use_system_env", True):
            self.log.debug("Skipping %s.", self.__class__.__name__)
            return

        launch_args = self.launch_context.launch_args
        if self.argument in launch_args:
            self.log.debug("%s already in launch arguments", self.argument)
            return

        # Insert right after the executable
        launch_args.insert(1, self.argument)
        self.log.info("Added %s to launch arguments", self.argument)
