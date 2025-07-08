
import bpy

from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError
)
import ayon_blender.api.action
from ayon_blender.api import plugin


class ValidateNoAnimation(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Ensure that meshes don't have animation data."""

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["blendScene", "model", "rig"]
    label = "No Animation"
    actions = [ayon_blender.api.action.SelectInvalidAction]

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        for obj in instance:
            if isinstance(obj, bpy.types.Object):
                if obj.animation_data and obj.animation_data.action:
                    invalid.append(obj)
        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            names = ", ".join(obj.name for obj in invalid)
            raise PublishValidationError(
                "Objects found in instance which have"
                f" animation data: {names}",
                title="Keyframes on Objects"
            )
