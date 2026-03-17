import bpy

import inspect
import pyblish.api

from ayon_core.pipeline.publish import (
    RepairContextAction,
    PublishValidationError
)

from ayon_blender.api import plugin, lib


class ValidateRenderlayerActive(plugin.BlenderContextPlugin):
    """Validate the state of view layers based on the instance's view layer definitions.
    If a view layer is expected to be active but is inactive, it will be flagged as invalid.
    Repair action would fix this issue by setting the view layers to their expected states
    according to the instance's definitions.

    """

    order = pyblish.api.ValidatorOrder
    hosts = ["blender"]
    label = "Validate Renderlayer Active"
    actions = [RepairContextAction]

    @staticmethod
    def get_required_viewlayers(context: pyblish.api.Context) -> set[str]:
        """Get the set of required view layers based on the instance's view
        layer definitions.

        Args:
            context (pyblish.api.Context): Context data

        Returns:
            set[str]: A set of required view layer nodes.
        """
        required_viewlayer_nodes = set()
        for instance in context:
            # Process only render instances
            if instance.data["productBaseType"] != "render":
                continue
            # Skip disabled instances
            if not instance.data.get("publish", True):
                continue
            comp_output_node: "bpy.types.CompositorNodeOutputFile" = (
                instance.data["transientData"]["instance_node"]
            )
            used_viewlayers = lib.get_upstream_viewlayers(comp_output_node)
            required_viewlayer_nodes.update(used_viewlayers)

        return required_viewlayer_nodes

    def process(self, context: pyblish.api.Context) -> None:
        """
        Validate the state of view layers based on the instance's view layer

        Args:
            context (pyblish.api.Context): Context data
        """
        invalid = self.get_invalid(context)
        if invalid:
            raise PublishValidationError(
                "Some view layers are not in the expected state.",
                title="Invalid view layer states",
                description=self.get_description(),
            )

    @classmethod
    def get_invalid(
        cls, context: pyblish.api.Context) -> list[bpy.types.ViewLayer]:
        """Get the list of invalid view layers based on the instance's view
        layer definitions.

        Args:
            context (pyblish.api.Context): Context data

        Returns:
            list[bpy.types.ViewLayer]: A list of invalid view layers.
        """
        invalid = []
        required_vl_nodes = cls.get_required_viewlayers(context)
        for viewlayer in bpy.context.scene.view_layers:
            is_required = viewlayer.name in required_vl_nodes
            if is_required and not viewlayer.use:
                cls.log.error(
                    f"View layer '{viewlayer.name}' is expected to be active but is inactive."
                )
                invalid.append(viewlayer)
        return invalid

    @classmethod
    def repair(cls, context: pyblish.api.Context) -> None:
        """Repair the state of view layers based on the instance's
        view layer definitions.

        Args:
            context (pyblish.api.Context): Context data

        """
        invalid = cls.get_invalid(context)
        for viewlayer in invalid:
            viewlayer.use = True

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
