"""Create a camera asset."""

import bpy

from ayon_blender.api import plugin, lib


class CreateCamera(plugin.BlenderCreator):
    """Single baked camera"""

    identifier = "io.ayon.creators.blender.camera"
    label = "Camera"
    description = __doc__
    product_type = "camera"
    icon = "video-camera"

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        # Run parent create method
        collection = super().create(
            product_name, instance_data, pre_create_data
        )

        if pre_create_data.get("use_selection"):
            selected_objects = lib.get_selection()
            for selected_object in selected_objects:
                collection.objects.link(selected_object)

            selected_collections = lib.get_selected_collections()
            for selected_collection in selected_collections:
                collection.children.link(selected_collection)
        else:
            # Create a camera
            plugin.deselect_all()
            camera = bpy.data.cameras.new(product_name)
            camera_obj = bpy.data.objects.new(product_name, camera)
            collection.objects.link(camera_obj)

            bpy.context.view_layer.objects.active = camera_obj

        return collection

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        return defs
