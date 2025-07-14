"""Create a pointcache asset."""

from ayon_blender.api import plugin, lib


class CreatePointcache(plugin.BlenderCreator):
    """Polygonal static geometry."""

    identifier = "io.ayon.creators.blender.pointcache"
    label = "Point Cache"
    product_type = "pointcache"
    icon = "gears"

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
        defs = lib.collect_animation_defs(self.create_context,
                                          step=False)

        return defs
