import bpy

import pyblish.api

from ayon_core.pipeline.publish import (
    RepairContextAction,
    PublishValidationError
)

from ayon_blender.api import plugin


class ValidateReviewRendererIsEevee(plugin.BlenderContextPlugin):
    """Validate Renderer is set to Eevee for Review.
    This ensures that the review renders are consistent and use the Eevee renderer.
    And avoid the potential attribute error raised from Cycles renderer.
    """

    order = pyblish.api.ValidatorOrder
    hosts = ["blender"]
    families = ["review"]
    label = "Validate Review Renderer Is Eevee"
    actions = [RepairContextAction]

    def process(self, context):
        if bpy.context.scene.render.engine == "CYCLES":
            raise PublishValidationError(
                "Review renderer must be set to Eevee.",
                title="Invalid Review Renderer"
            )

    def repair(self, context):
        bpy.context.scene.render.engine = "BLENDER_EEVEE"
