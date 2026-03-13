import bpy

import inspect
import pyblish.api

from ayon_core.pipeline.publish import (
    RepairContextAction,
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
    actions = [RepairContextAction]

    @staticmethod
    def _get_expected_viewlayers(context: pyblish.api.Context) -> set[str]:
        all_viewlayers = set()
        for instance in context:
            viewlayers = instance.data.get("viewlayers")
            if not viewlayers:
                raise PublishValidationError(
                    title="Missing viewlayers node",
                    message=(
                        f"Instance '{instance.name}' is missing the 'viewlayers' node. "
                        "This attribute is required to validate the active state of "
                        "the view layers."
                    ),
                )
            all_viewlayers.update(viewlayers)
        return all_viewlayers

    def process(self, context: pyblish.api.Context):
        all_viewlayers = self._get_expected_viewlayers(context)
        if not all_viewlayers:
            raise PublishValidationError(
                title="No view layers defined in any instance",
                message=(
                    "No view layers are defined in any instance's viewlayers node. "
                    "Please define view layers in the instance nodes to validate the active state."
                ),
                description=self.get_description()
            )
        invalid_inactive = self.get_invalid_active_viewlayers(all_viewlayers)
        if  invalid_inactive:
            raise PublishValidationError(
                title="No viewlayer node found for instance",
                message=(
                    "No viewlayer node found for instance. "
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
            and vl.mute
        ]
        for vl in invalid:
            self.log.debug(f"View layer {vl.name} is inactive but should be active.")
        return invalid

    @classmethod
    def repair(cls, context: pyblish.api.Context):
        active = True
        all_viewlayers = cls._get_expected_viewlayers(context)
        for vl in bpy.context.scene.view_layers:
            if vl.name in all_viewlayers:
                vl.use = active
                vl.mute = not active
            cls.log.info(f"Set view layer {vl.name} to {vl.use}.")

    @staticmethod
    def get_description():
        return inspect.cleandoc("""
        ### No viewlayer node found for instance
        The active state of the view layers does not match the expected state based on the
        viewlayers node. This can lead to incorrect rendering results.
        Use the Repair action to set the correct active state for the view layers.
        """)
