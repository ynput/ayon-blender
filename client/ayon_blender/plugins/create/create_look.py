"""Create a Look asset."""

import bpy

from ayon_blender.api import lib, plugin


class CreateLook(plugin.BlenderCreator):
    """Look output for character"""

    identifier = "io.ayon.creators.blender.look"
    label = "Look"
    description = __doc__
    product_type = "look"
    product_base_type = "look"
    icon = "male"

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        # Run parent create method
        collection = super().create(
            product_name, instance_data, pre_create_data
        )
        if pre_create_data.get("use_selection"):
            for obj in lib.get_selection():
                if not obj.active_material:
                    empty_material = bpy.data.materials.new(name=product_name)
                    empty_material.use_nodes = True
                    obj.data.materials.append(empty_material)
                else:
                    obj.active_material.name = product_name

                if isinstance(obj, bpy.types.Object):
                    collection.objects.link(obj)

        return collection
