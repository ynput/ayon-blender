from typing import Optional

import pyblish.api
import bpy
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    RepairAction,
    PublishValidationError
)
from ayon_blender.api.pipeline import set_resolution


class ValidateResolutionSetting(pyblish.api.InstancePlugin,
                                OptionalPyblishPluginMixin):
    """Validate the resolution setting aligned with DB"""

    order = pyblish.api.ValidatorOrder - 0.01
    families = ["render", "review"]
    hosts = ["blender"]
    label = "Validate Resolution"
    optional = True
    actions = [RepairAction]

    def process(self, instance: pyblish.api.Instance) -> None:
        if not self.is_active(instance.data):
            return

        folder_resolution = self.get_folder_resolution(instance)
        if folder_resolution is None:
            self.log.debug(
                "Skipping resolution validation for instance '%s': no "
                "resolutionWidth/resolutionHeight set on the task or "
                "folder entity.", instance.name
            )
            return

        width, height = folder_resolution
        current_width, current_height = self.get_current_resolution()

        if (current_width, current_height) != (width, height):
            raise PublishValidationError(
                "Resolution setting is incorrect.\n\n"
                f"Current resolution: {current_width}x{current_height}\n"
                f"Expected resolution: {width}x{height}\n\n"
                "The expected resolution is set on the asset or shot. "
                "You can use the repair action to set it.",
                title="Resolution Setting incorrect",
            )

    def get_current_resolution(self) -> tuple[int, int]:
        """Get the current resolution from the instance data.

        Returns:
            tuple[int, int]: The current resolution (width, height).
        """
        return (
            bpy.context.scene.render.resolution_x,
            bpy.context.scene.render.resolution_y,
        )

    @classmethod
    def get_context_resolution(
        cls,
        instance: pyblish.api.Instance
    ) -> Optional[tuple[int, int]]:
        """Get the resolution set on the folder (task entity).

        Args:
            instance (pyblish.api.Instance): The instance to get the
                folder resolution from.

        Returns:
            Optional[tuple[int, int]]: The resolution set on the entity
                (width, height), or None when the task/folder entity does
                not define a resolution.
        """
        entity = (
            instance.data.get("taskEntity")
            or instance.data.get("folderEntity")
        )
        if entity:
            attributes = entity.get("attrib") or {}
            width = attributes.get("resolutionWidth")
            height = attributes.get("resolutionHeight")
            if width is not None and height is not None:
                return int(width), int(height)

        return None

    @classmethod
    def repair(cls, instance: pyblish.api.Instance) -> None:
        """Repair the resolution setting for the instance.

        Args:
            instance (pyblish.api.Instance): The instance to repair
                the resolution for.
        """
        entity = (
            instance.data.get("taskEntity")
            or instance.data.get("folderEntity")
        )
        if not entity:
            cls.log.debug(
                "Skipping resolution repair for instance '%s': no task or "
                "folder entity available.", instance.name
            )
            return

        set_resolution(entity)
