"""Create a Blender scene asset."""
import bpy
from ayon_blender.api import plugin, lib


class CreateBlendScene(plugin.BlenderCreator):
    """Generic group of assets."""

    identifier = "io.ayon.creators.blender.blendscene"
    label = "Blender Scene"
    product_type = "blendScene"
    icon = "cubes"

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):

        instance_node = super().create(product_name,
                                       instance_data,
                                       pre_create_data)

        if pre_create_data.get("use_selection"):
            selected_objects = lib.get_selection()
            for selected_object in selected_objects:
                instance_node.objects.link(selected_object)

            selected_collections = lib.get_selected_collections()
            for selected_collection in selected_collections:
                instance_node.children.link(selected_collection)

        return instance_node
