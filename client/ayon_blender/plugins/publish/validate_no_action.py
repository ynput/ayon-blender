
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


class ValidateNoAction(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Ensure that objects have action with animation data."""

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["blendScene", "model", "rig"]
    label = "No Action"
    actions = [SelectInvalidAction, RepairAction]

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        for data in instance:
            if not (
                isinstance(data, bpy.types.Object) and data.type in
                {'MESH', 'EMPTY', 'ARMATURE'}
            ):
                continue
            # just in case the instance node contains either Armature or top empty
            child = data.children[0] if data.children else data
            if child and child.type == 'ARMATURE':
                if not child.animation_data:
                    invalid.append(child)
                else:
                    if not child.animation_data.action:
                        invalid.append(child)

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
                f" no action: {names}",
                title="No Action found on Objects",
                description=self.get_description()
            )

    def get_description(self):
        return inspect.cleandoc("""
            ### No Action found on Objects
            Objects must contain any action data.
            Please add the action to the objects before publishing.
        """)

    @classmethod
    def repair(cls, instance):
        for data in instance:
            data.animation_data_create()
        cls.log.info("Created action data for objects in instance.")
