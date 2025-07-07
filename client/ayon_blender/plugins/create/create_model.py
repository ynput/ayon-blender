"""Create a model asset."""

from ayon_blender.api import plugin, lib


class CreateModel(plugin.BlenderCreator):
    """Polygonal static geometry."""

    identifier = "io.openpype.creators.blender.model"
    label = "Model"
    product_type = "model"
    icon = "cube"

    create_as_asset_group = True

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        asset_group = super().create(product_name,
                                     instance_data,
                                     pre_create_data)

        # Add selected objects to instance
        if pre_create_data.get("use_selection"):
            selections = lib.get_selection()
            top_root = lib.get_highest_root(selections)
            top_root.parent = asset_group

        return asset_group
