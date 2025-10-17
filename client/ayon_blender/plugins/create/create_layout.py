"""Create a layout asset."""

import bpy

from ayon_blender.api import plugin, lib


class CreateLayout(plugin.BlenderCreator):
    """Layout output for character rigs"""

    identifier = "io.ayon.creators.blender.layout"
    label = "Layout"
    description = __doc__
    product_type = "layout"
    icon = "cubes"

    create_as_asset_group = True

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):

        asset_group = super().create(product_name,
                                     instance_data,
                                     pre_create_data)

        # Add selected objects to instance
        if pre_create_data.get("use_selection"):
            bpy.context.view_layer.objects.active = asset_group
            for obj in lib.get_selection():
                obj.parent = asset_group

        return asset_group
