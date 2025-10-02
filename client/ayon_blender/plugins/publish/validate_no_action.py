
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
    families = ["action"]
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
                    cls.log.error(f"No animation data: {child.name}")
                    invalid.append(child)
                else:
                    product_name = instance.data["productName"]
                    if not child.animation_data.action:
                        cls.log.error(f"No action data: {child.name}")
                        invalid.append(child)
                    elif not child.animation_data.action.name.startswith(product_name):
                        cls.log.error(
                            f"Action name mismatch: {product_name} ({child.animation_data.action.name})"
                        )
                        invalid.append(child)
        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            self.log.debug("Skipping Validate No Action...")
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
        product_name = instance.data["productName"]
        invalid_object = cls.get_invalid(instance)
        for obj in invalid_object:
            if not obj.animation_data:
                obj.animation_data_create()
            if not obj.animation_data.action:
                action = bpy.data.actions.new(name=product_name)
                obj.animation_data.action = action
            else:
                obj.animation_data.action.name = product_name
        cls.log.info("Created action data for objects in instance.")
