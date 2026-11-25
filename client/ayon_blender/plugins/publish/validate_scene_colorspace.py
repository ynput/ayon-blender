import inspect
import math

import bpy
import pyblish.api

from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import (
    RepairContextAction,
    ValidateContentsOrder,
    PublishValidationError,
)

from ayon_blender.api import plugin
from ayon_blender.api.pipeline import set_colorspace_from_settings


class ValidateSceneColorspace(plugin.BlenderContextPlugin,
                              OptionalPyblishPluginMixin):
    """Validate the scene color management matches the workfile settings.

    Checks the display, view, exposure, gamma and working space (Blender
    5.0+) against the workfile color management settings, skipping empty
    values.

    Does nothing when the workfile color management settings are disabled.
    """

    label = "Validate Scene Colorspace"
    order = ValidateContentsOrder
    hosts = ["blender"]
    optional = True
    actions = [RepairContextAction]

    def process(self, context: pyblish.api.Context):
        if not self.is_active(context.data):
            self.log.debug("Skipping Validate Scene Colorspace...")
            return

        invalid = self.get_invalid(context)
        if invalid:
            bullet_points = "\n".join(f"- {error}" for error in invalid)
            raise PublishValidationError(
                f"Scene color management is incorrect:\n{bullet_points}",
                title="Scene colorspace incorrect",
                description=self.get_description(bullet_points),
            )

    @classmethod
    def get_invalid(cls, context: pyblish.api.Context) -> list[str]:
        workfile_settings = (
            context.data["project_settings"]["blender"]["imageio"]["workfile"]
        )
        if not workfile_settings["enabled"]:
            cls.log.debug("Workfile color management settings are disabled.")
            return []

        scene = bpy.context.scene
        checks = [
            ("Display", scene.display_settings.display_device,
             workfile_settings["display"]),
            ("View", scene.view_settings.view_transform,
             workfile_settings["view"]),
            ("Exposure", scene.view_settings.exposure,
             workfile_settings["exposure"]),
            ("Gamma", scene.view_settings.gamma,
             workfile_settings["gamma"]),
        ]
        # Blender 4.x has no per blend file working space, it was added in
        # Blender 5.0. Remove this check once Blender 4 is no longer supported.
        if hasattr(bpy.data, "colorspace"):
            checks.append((
                "Working space", bpy.data.colorspace.working_space,
                workfile_settings["working_space"]
            ))

        invalid = []
        for label, current, expected in checks:
            if isinstance(current, float):
                # Blender stores these as 32-bit floats, e.g. 0.8 reads back
                # as 0.800000011920929.
                if math.isclose(current, expected, rel_tol=1e-6, abs_tol=1e-6):
                    continue
                error = f"{label} is {current:g} but should be {expected:g}."
            elif expected == "" or current == expected:
                continue
            else:
                error = f"{label} is '{current}' but should be '{expected}'."
            cls.log.error(error)
            invalid.append(error)
        return invalid

    @classmethod
    def repair(cls, context: pyblish.api.Context):
        set_colorspace_from_settings(context.data["project_settings"]["blender"])

    @staticmethod
    def get_description(bullet_points: str) -> str:
        return inspect.cleandoc(
            """### Scene color management is incorrect

            The scene color management does not match the workfile color
            management settings of the project:

            {bullet_points}

            Use the Repair action to apply the workfile color management
            settings.
            """
        ).format(bullet_points=bullet_points)
