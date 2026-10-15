import os

import pyblish.api

from ayon_core.host.interfaces import SaveWorkfileOptionalData
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.workfile import save_next_version
from ayon_blender.api import plugin


class IncrementWorkfileVersion(
    plugin.BlenderContextPlugin,
    OptionalPyblishPluginMixin
):
    """Increment current workfile version."""

    order = pyblish.api.IntegratorOrder + 0.9
    label = "Increment Workfile Version"
    optional = True
    hosts = ["blender"]
    families = ["animation", "model", "rig", "action", "layout", "blendScene",
                "pointcache", "render.farm"]

    def process(self, context):
        if not self.is_active(context.data):
            return

        assert all(result["success"] for result in context.data["results"]), (
            "Publishing not successful so version is not increased.")

        current_filepath: str = context.data["currentFile"]
        current_filename = os.path.basename(current_filepath)
        save_next_version(
            description=(
                f"Incremented by publishing from {current_filename}"
            ),
            # Optimize the save by reducing needed queries for context
            prepared_data=SaveWorkfileOptionalData(
                project_entity=context.data["projectEntity"],
                project_settings=context.data["project_settings"],
                anatomy=context.data["anatomy"],
            )
        )
