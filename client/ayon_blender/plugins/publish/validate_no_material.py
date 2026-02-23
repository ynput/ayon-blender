
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
        # just in case the instance node contains either Armature or top empty

        product_name = instance.data["productName"]
        for data in instance:
            if not (
                isinstance(data, bpy.types.Object) and data.type in {
                    "MESH", "MATERIAL"
                }
            ):
                continue
            child = data.children[0] if data.children else data
            cls.log.debug(f"Checking object: {child.name} with material: ")
            if not child.active_material:
                cls.log.error(f"No active material: {child.name}")
                invalid.append(child)
            if child.active_material.name != product_name:
                cls.log.error(
                    f"Material name mismatch: {product_name} "
                    f"({child.active_material.name})"
                )
                invalid.append(child)
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
            if obj.active_material.name != instance.data["productName"]:
                obj.active_material.name = product_name
