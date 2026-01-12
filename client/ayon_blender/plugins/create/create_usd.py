"""Create a USD Export."""

import bpy
from ayon_core.lib import BoolDef
from ayon_blender.api import plugin, lib


class CreateUSD(plugin.BlenderCreator):
    """Create USD Export"""

    identifier = "io.ayon.creators.blender.usd"
    name = "usdMain"
    label = "USD"
    description = __doc__
    product_type = "usd"
    product_base_type = "usd"
    icon = "gears"

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        # Run parent create method
        collection = super().create(
            product_name, instance_data, pre_create_data
        )

        objects = []
        selected_collections = []
        if pre_create_data.get("use_selection"):
            objects = lib.get_selection()
            selected_collections = lib.get_selected_collections()

        # Create template hierarchy
        if pre_create_data.get("createAssetTemplateHierarchy", False):
            folder_path = instance_data["folderPath"]
            folder_name = folder_path.rsplit("/", 1)[-1]

            root = bpy.data.objects.new(folder_name, object_data=None)
            bpy.context.scene.collection.objects.link(root)

            geo = bpy.data.objects.new("geo", object_data=None)
            bpy.context.scene.collection.objects.link(geo)
            geo.parent = root

            # Parent members with geo.
            for obj in objects:
                obj.parent = geo

            # Override the objects list to include only the root object.
            objects = [root]

        for obj in objects:
            collection.objects.link(obj)

        for selected_collection in selected_collections:
            collection.children.link(selected_collection)

        return collection

    def get_pre_create_attr_defs(self):
        defs = super().get_pre_create_attr_defs()
        defs.extend([
            BoolDef("createAssetTemplateHierarchy",
                    label="Create asset hierarchy",
                    tooltip=(
                        "Create the root hierarchy for '{folder_name}/geo'"
                        " as per the USD Asset Structure guidelines to"
                        " add your geometry into."
                    ),
                    default=False)
        ])
        return defs