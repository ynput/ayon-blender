import bpy

import inspect
import pyblish.api

from ayon_core.pipeline.publish import (
    RepairAction,
    PublishValidationError
)

from ayon_blender.api import plugin


class ValidateRenderlayerActive(plugin.BlenderContextPlugin):
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

    def process(self, context: pyblish.api.Context):
        all_viewlayers = set()
        for instance in context:
            viewlayers = instance.data.get("viewlayers")
            if not viewlayers:
                all_viewlayers = {
                    vl.name for vl in bpy.context.scene.view_layers
                }
            all_viewlayers.update(viewlayers)

        # TODO: find all the invalid view layers by instance node
        invalid_active = self.get_invalid_active_viewlayers(all_viewlayers)
        invalid_inactive = self.get_invalid_inactive_viewlayers(all_viewlayers)
        if invalid_active or invalid_inactive:
            raise PublishValidationError(
                title="Renderlayer active state does not match the viewlayers attribute",
                message=(
                    "Some view layers are active but should be inactive, or vice versa. "
                    "Use the Repair action to set the correct active state for the "
                    "view layers."
                ),
                description=self.get_description()
            )

    def get_invalid_active_viewlayers(self, viewlayers: list[str]):
        """Get view layers that are inactive but should be active.

        Args:
            viewlayers (list[str]): viewlayers from the instance,
            which defines the expected active view layers.

        Returns:
            list[bpy.types.ViewLayer]: list of view layers that are inactive
            but should be active.
        """
        invalid = [
            vl for vl in bpy.context.scene.view_layers
            if vl.name in viewlayers and not vl.use
        ]
        for vl in invalid:
            self.log.debug(f"View layer {vl.name} is inactive but should be active.")
        return invalid


    @classmethod
    def repair(cls, context: pyblish.api.Context):
        all_viewlayers = set()
        for instance in context:
            viewlayers = instance.data.get("viewlayers")
            if not viewlayers:
                all_viewlayers = {
                    vl.name for vl in bpy.context.scene.view_layers
                }
            all_viewlayers.update(viewlayers)
        for vl in bpy.context.scene.view_layers:
            should_be_active = vl.name in all_viewlayers
            if vl.use != should_be_active:
                vl.use = should_be_active
                state = "active" if should_be_active else "inactive"
                cls.log.info(f"Set view layer {vl.name} to {state}.")

    @staticmethod
    def get_description():
        return inspect.cleandoc("""
        "### Renderlayer Active State Mismatch
        The active state of the view layers does not match the expected state based on the
        viewlayers attribute. This can lead to incorrect rendering results.
        Use the Repair action to set the correct active state for the view layers.
        """)
