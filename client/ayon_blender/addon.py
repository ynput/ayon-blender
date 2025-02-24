import os
from ayon_core.addon import AYONAddon, IHostAddon

from .version import __version__

BLENDER_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class BlenderAddon(AYONAddon, IHostAddon):
    name = "blender"
    version = __version__
    host_name = "blender"

    def add_implementation_envs(self, env, _app):
        """Modify environments to contain all required for implementation."""
        # Prepare path to implementation script
        implementation_script_path = os.path.join(
            BLENDER_ADDON_ROOT,
            "blender_addon"
        )

        # Add blender implementation script path to PYTHONPATH
        python_path = env.get("PYTHONPATH") or ""
        python_path_parts = [
            path
            for path in python_path.split(os.pathsep)
            if path
        ]
        python_path_parts.insert(0, implementation_script_path)
        env["PYTHONPATH"] = os.pathsep.join(python_path_parts)

        # TODO: What setting or flag will we user before launching Blender
        #  to define whether it supports the new BLENDER_SYSTEM_SCRIPTS
        #  with multiple paths?
        supports_blender_system_scripts = True
        if supports_blender_system_scripts:
            self.configure_blender_env(env, implementation_script_path)
        else:
            # Old versions of Blender had broken BLENDER_SYSTEM_SCRIPTS
            # nor supported multiple paths for it. See:
            # https://projects.blender.org/blender/blender/issues/127013
            self.configure_blender_pre_44_env(env, implementation_script_path)

        # Define Qt binding if not defined
        env.pop("QT_PREFERRED_BINDING", None)

    def configure_blender_pre_44_env(
        self, env: dict, implementation_script_path: str
    ):
        # Modify Blender user scripts path
        previous_user_scripts = set()
        # Implementation path is added to set for easier paths check inside
        #   loops - will be removed at the end
        previous_user_scripts.add(implementation_script_path)

        ayon_blender_user_scripts = env.get("AYON_BLENDER_USER_SCRIPTS") or ""
        for path in ayon_blender_user_scripts.split(os.pathsep):
            if path:
                previous_user_scripts.add(os.path.normpath(path))

        blender_user_scripts = env.get("BLENDER_USER_SCRIPTS") or ""
        for path in blender_user_scripts.split(os.pathsep):
            if path:
                previous_user_scripts.add(os.path.normpath(path))

        # Remove implementation path from user script paths as is set to
        #   `BLENDER_USER_SCRIPTS`
        previous_user_scripts.remove(implementation_script_path)
        env["BLENDER_USER_SCRIPTS"] = implementation_script_path

        # Set custom user scripts env
        env["AYON_BLENDER_USER_SCRIPTS"] = os.pathsep.join(
            previous_user_scripts
        )

    def configure_blender_env(
        self, env: dict, implementation_script_path: str
    ):
        # With Blender 4.4+ we can just use BLENDER_SYSTEM_SCRIPTS
        paths = [implementation_script_path]

        # Support older AYON_BLENDER_USER_SCRIPTS for compatibility
        if env.get("AYON_BLENDER_USER_SCRIPTS"):
            # Note that we `pop` the AYON_BLENDER_USER_SCRIPTS to avoid
            # the legacy post-Blender launch logic script to trigger which
            # is incompatible with Blender 4.4+
            paths.append(env.pop("AYON_BLENDER_USER_SCRIPTS"))

        # Preserve existing BLENDER_SYSTEM_SCRIPTS, append them at the end
        if env.get("BLENDER_SYSTEM_SCRIPTS"):
            paths.append(env.get("BLENDER_SYSTEM_SCRIPTS"))

        # Set custom user scripts env
        env["BLENDER_SYSTEM_SCRIPTS"] = os.pathsep.join(paths)

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [
            os.path.join(BLENDER_ADDON_ROOT, "hooks")
        ]

    def get_workfile_extensions(self):
        return [".blend"]
