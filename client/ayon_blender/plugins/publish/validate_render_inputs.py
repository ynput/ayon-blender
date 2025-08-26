import inspect

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
    # TODO: Not sure how to select a Compositor Node through Python API so
    #       until then, we can't select the node via the UI.
    # actions = [SelectInvalidAction]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)

        if invalid:

            node = invalid[0].node
            node_name = node.name

            labels = []
            for socket in invalid:
                label = socket.name
                labels.append(label)

            raise PublishValidationError(
                f"The Compositor File Output Node '{node_name}' has the "
                "following unconnected image slots:\n{}".format(
                    "\n".join(f"- {label}" for label in labels)
                ),
                title="Unconnected image slots",
                description=self.get_description(),
            )

    @classmethod
    def get_invalid(cls, instance):
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

        return invalid

    @staticmethod
    def get_description():
        return inspect.cleandoc("""### Unconnected image slots
        
        The Compositor File Output Node has unconnected input image slots.
        Make sure to connect each of the individual slots to an input, or
        remove the irrelevant slots if they are not needed.
        """)
