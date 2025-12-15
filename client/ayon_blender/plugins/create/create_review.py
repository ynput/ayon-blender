"""Create review."""

from ayon_blender.api import plugin, lib


class CreateReview(plugin.BlenderCreator):
    """Render viewport preview for review purposes"""

    identifier = "io.ayon.creators.blender.review"
    label = "Review"
    description = __doc__
    product_type = "review"
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

        return collection

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)

        return defs

    def get_publish_families(self):
        return ["review", "review.playblast"]
