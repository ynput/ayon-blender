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
    label = "Validate Resolution Setting"
    optional = True
    actions = [RepairAction]

    def process(self, instance: pyblish.api.Instance) -> None:
        if not self.is_active(instance.data):
            return
        width, height = self.get_folder_resolution(instance)
        current_width, current_height = self.get_current_resolution()
        if current_width != width and current_height != height:
            raise PublishValidationError("Resolution Setting "
                                         "not matching resolution "
                                         "set on asset or shot.")
        if current_width != width:
            raise PublishValidationError("Width in Resolution Setting "
                                         "not matching resolution set "
                                         "on asset or shot.")

        if current_height != height:
            raise PublishValidationError("Height in Resolution Setting "
                                         "not matching resolution set "
                                         "on asset or shot.")

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
    def get_folder_resolution(
        cls, instance: pyblish.api.Instance) -> tuple[int, int]:
        """Get the resolution set on the folder (task entity).

        Args:
            instance (pyblish.api.Instance): The instance to get the
                folder resolution from.

        Returns:
            tuple[int, int]: The resolution set on the folder (width, height).
        """
        entity = (
            instance.data.get("taskEntity")
            or instance.data.get("folderEntity")
        )
        if entity:
            attributes = entity["attrib"]
            width = attributes.get("resolutionWidth")
            height = attributes.get("resolutionHeight")
            if width is not None and height is not None:
                return int(width), int(height)

        # Defaults if not found in folder entity
        return 1920, 1080

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
        if entity:
            set_resolution(entity)
        else:
            scene = bpy.context.scene
            scene.render.resolution_x = 1920
            scene.render.resolution_y = 1080
