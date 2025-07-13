import bpy

import pyblish.api

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError
)
from ayon_blender.api import plugin


class ValidateRenderCompositorNodeFileOutputConnected(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Validate the Compositor File Output Node has all its image slots
    connected to an input."""

    order = pyblish.api.ValidatorOrder
    hosts = ["blender"]
    families = ["render"]
    label = "Validate Render Inputs"
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        output: bpy.types.CompositorNodeOutputFile = (
            instance.data["transientData"]["instance_node"]
        )

        # Check all the slots are connected
        invalid = []
        for input_ in output.inputs:
            # Assume all `NodeSocketColor` entries have inputs.
            # TODO: Validate only entries that relate to the `slots`, but how?
            if isinstance(input_, bpy.types.NodeSocketColor):
                if not input_.links:
                    invalid.append(input_)


        if invalid:
            raise PublishValidationError(
                "The Compositor File Output Node has the following "
                "unconnected image slots: {}".format(
                    ", ".join(str(socket) for socket in invalid)
                )
            )
