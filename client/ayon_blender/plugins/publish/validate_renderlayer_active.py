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

    def process(self, context: pyblish.api.Context) -> None:
        """
        Validate the state of view layers based on the instance's view layer

        Args:
            context (pyblish.api.Context): Context data
        """
        enabled_compositor_nodes = self.get_enabled_compositor_nodes(context)
        if not enabled_compositor_nodes:
            # No render instances enabled, nothing to validate
            return

        invalid = self.get_invalid(enabled_compositor_nodes)
        if invalid:
            raise PublishValidationError(
                "Some view layers are not in the expected state.",
                title="Invalid view layer states",
                description=self.get_description(),
            )

    @staticmethod
    def get_enabled_compositor_nodes(
        context: pyblish.api.Context
    ) -> set["bpy.types.CompositorNodeOutputFile"]:
        """Return Compositor File Output nodes that are associated with
        enabled render instances."""
        nodes = set()
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
            nodes.add(comp_output_node)
        return nodes

    @classmethod
    def get_invalid(
        cls,
        enabled_compositor_nodes: set["bpy.types.CompositorNodeOutputFile"]
    ) -> list[bpy.types.ViewLayer]:
        """Get the list of invalid view layers based on the instance's view
        layer definitions.

        Args:
            enabled_compositor_nodes: Compositor File Output nodes that
                are associated with enabled render instances.

        Returns:
            list[bpy.types.ViewLayer]: A list of invalid view layers.
        """

        required_viewlayers = set()
        for comp_output_node in enabled_compositor_nodes:
            used_viewlayers = lib.get_upstream_viewlayers(comp_output_node)
            required_viewlayers.update(used_viewlayers)

        invalid = []
        for viewlayer in bpy.context.scene.view_layers:
            is_required = viewlayer.name in required_viewlayers
            if viewlayer.use != is_required:
                active_label = "active" if viewlayer.use else "inactive"
                required_label = "active" if is_required else "inactive"

                cls.log.error(
                    f"View layer '{viewlayer.name}' is expected to"
                    f" be {required_label} but is {active_label}."
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
            # Toggle from the invalid state
            viewlayer.use = not viewlayer.use

    def get_description(self):
        return inspect.cleandoc(
            """### Disabled view layers are required for rendering
            Some view layers are disabled while being used for rendering outputs
            through File Output nodes.
            The repair action will enable them for rendering,
            ensuring valid outputs are produced once submitted.
            """
    )
