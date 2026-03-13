import bpy

import inspect
import pyblish.api

from ayon_core.pipeline.publish import (
    RepairAction,
    PublishValidationError
)

from ayon_blender.api import plugin, lib


class ValidateRenderlayerActive(plugin.BlenderInstancePlugin):
    """Validate Renderlayer active or inactive when renderlayer attribute
    definition has been filled.
    - If view layer is in the viewlayers attribute, it should be active.
    - If view layer is not in the viewlayers attribute, it should be inactive.

    """

    order = pyblish.api.ValidatorOrder
    hosts = ["blender"]
    families = ["render"]
    label = "Validate Renderlayer Active"
    actions = [RepairAction]

    def process(self, instance: pyblish.api.Instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Some view layers are not in the expected state.",
                message=(
                    "Some view layers are not in the expected state. "
                    "Please see description for details."
                ),
                description=self.get_description(),
            )

    @classmethod
    def get_invalid(cls, instance: pyblish.api.Instance):
        invalid = []
        comp_output_node: "bpy.types.CompositorNodeOutputFile" = (
            instance.data["transientData"]["instance_node"])
        vl_node_by_viewlayer = lib.get_viewlayer_nodes(comp_output_node)
        for viewlayer in bpy.context.scene.view_layers:
            if viewlayer.name not in vl_node_by_viewlayer:
                continue

            vl_node = vl_node_by_viewlayer[viewlayer.name]
            if not viewlayer.use or vl_node.mute:
                invalid.append((viewlayer, vl_node))

        return invalid

    @classmethod
    def repair(cls, instance: pyblish.api.Instance):
        invalid = cls.get_invalid(instance)
        for viewlayer, vl_node in invalid:
            viewlayer.use = True
            vl_node.mute = False

    def get_description(self):
        return inspect.cleandoc(
            """### Some view layers are not in the expected state.
            This validation checks the state of view layers based on the instance's
            view layer definitions. If a view layer is expected to be active
            but is inactive, or vice versa, it will be flagged as invalid.
            Repair action would fix this issue by setting the view layers
            to their expected states according to the instance's definitions.
            """
    )