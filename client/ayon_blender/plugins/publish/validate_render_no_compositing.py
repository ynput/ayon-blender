import bpy

import pyblish.api

from ayon_core.pipeline.publish import (
    RepairAction,
    PublishValidationError
)

from ayon_blender.api import plugin


class ValidateRenderNoCompositing(plugin.BlenderInstancePlugin):
    """Validate Post Processing > Compositing checkbox
    is enabled in the render settings.

    This is required as the rendering workflow relies on the compositing
    nodes to process the final render.
    """

    order = pyblish.api.ValidatorOrder
    hosts = ["blender"]
    families = ["render"]
    label = "Validate Render No Compositing"
    actions = [RepairAction]

    def process(self, instance):
        if not bpy.context.scene.render.use_compositing:
            raise PublishValidationError(
                title="Post Processing > Compositing checkbox is disabled",
                message="Post Processing > Compositing checkbox is disabled.",
                description=(
                    "### Post Processing > Compositing Disabled\n\n"
                    "As the rendering workflow relies on the compositing nodes to process "
                    "the final render, it is essential to have the compositing checkbox "
                    "enabled in the render settings. "
                    "Use the Repair action to enable the compositing checkbox."
                )
            )

    @classmethod
    def repair(cls, instance):
        bpy.context.scene.render.use_compositing = True
