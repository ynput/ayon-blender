
import bpy
import inspect
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishValidationError,
    RepairAction,
)
from ayon_blender.api.action import SelectInvalidAction

from ayon_blender.api import plugin


class ValidateNoMaterial(plugin.BlenderInstancePlugin):
    """Ensure that objects have material assigned."""

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["look"]
    label = "No Material"
    actions = [SelectInvalidAction, RepairAction]

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        for obj in instance:
            if not (
                isinstance(obj, bpy.types.Object)
                and hasattr(obj.data, "materials")
            ):
                continue
            if not obj.active_material:
                cls.log.error(f"No active material: {obj.name}")
                invalid.append(obj)
        return invalid

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            names = ", ".join(obj.name for obj in invalid)
            raise PublishValidationError(
                "Objects found in instance which have"
                f" no material: {names}",
                title="No Material Assigned on Objects",
                description=self.get_description()
            )

    def get_description(self):
        return inspect.cleandoc("""
            ### No Material Assigned to Objects
            Objects must have a material assigned.
            Please assign a material to the objects before publishing.
        """
        )

    @classmethod
    def repair(cls, instance):
        product_name = instance.data["productName"]
        invalid_object = cls.get_invalid(instance)
        for obj in invalid_object:
            if not obj.active_material:
                empty_material = bpy.data.materials.new(name=product_name)
                empty_material.use_nodes = True
                obj.data.materials.append(empty_material)
