"""Create an animation asset."""

from ayon_blender.api import plugin, lib


class CreateAnimation(plugin.BlenderCreator):
    """Animation output for character rig"""

    identifier = "io.ayon.creators.blender.animation"
    label = "Animation"
    description = __doc__
    product_type = "animation"
    icon = "male"

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
        elif pre_create_data.get("asset_group"):
            # Use for Load Blend automated creation of animation instances
            # upon loading rig files
            obj = pre_create_data.get("asset_group")
            collection.objects.link(obj)

        return collection

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context,
                                          step=False)
        return defs
