
import bpy
import inspect
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
)
from ayon_blender.api.action import SelectInvalidAction

from ayon_blender.api import plugin


class ValidateNoAnimation(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Ensure that meshes do not have animation data."""

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["blendScene", "model", "rig"]
    label = "No Animation"
    optional = True
    actions = [SelectInvalidAction, RepairAction]

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
            self.log.debug("Skipping Validate No Animation...")
            return

        invalid = self.get_invalid(instance)
        if invalid:
            names = ", ".join(obj.name for obj in invalid)
            raise PublishValidationError(
                "Objects found in instance which have"
                f" animation data: {names}",
                title="Keyframes on Objects",
                description=self.get_description()
            )

    def get_description(self):
        return inspect.cleandoc("""
            ### Keyframes on Objects

            Objects must not contain any keyframe animation data.
            Please remove all keyframes before publishing.
        """)

    @classmethod
    def repair(cls, instance):
        invalid_objects = cls.get_invalid(instance)
        for obj in invalid_objects:
            obj.animation_data.action = None
