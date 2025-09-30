"""Create an animation asset."""

import bpy

from ayon_blender.api import lib, plugin


class CreateAction(plugin.BlenderCreator):
    """Action output for character rig"""

    identifier = "io.ayon.creators.blender.action"
    label = "Action"
    description = __doc__
    product_type = "action"
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
                if (obj.animation_data is not None
                        and obj.animation_data.action is not None):

                    empty_obj = bpy.data.objects.new(name=product_name,
                                                     object_data=None)
                    empty_obj.animation_data_create()
                    empty_obj.animation_data.action = obj.animation_data.action
                    empty_obj.animation_data.action.name = product_name
                    collection.objects.link(empty_obj)
                else:
                    if isinstance(obj, bpy.types.Object):
                        collection.objects.link(obj)


        return collection
