"""Create render."""
import bpy

from ayon_core.pipeline import AYON_CONTAINER_ID
from ayon_core.pipeline.create import CreatedInstance

from ayon_blender.api import plugin, lib
from ayon_blender.api.render_lib import prepare_rendering


class CreateRenderlayer(plugin.BlenderCreator):
    """Create render instance."""

    identifier = "io.openpype.creators.blender.render"
    label = "Render"
    product_type = "render"
    icon = "eye"

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        # TODO: Create compositor node and imprint there.
        # Create a compositor `CompositorNodeOutputFile` node as instance node
        # And pre-connect any existing passes according to settings.
        # It's important this does not mess up other existing networks in the
        # compositing node tree, so that it remains non-destructive.
        # TODO: Do not override scene render engine (unless explicitly enabled)

        try:
            # Run parent create method
            collection = super().create(
                product_name, instance_data, pre_create_data
            )

            prepare_rendering(collection)
        except Exception:
            # Remove the instance if there was an error
            bpy.data.collections.remove(collection)
            raise

        return collection

    def collect_instances(self):

        # Collect regularly
        super().collect_instances()

        # TODO: Convert legacy instances so that they are imprinted on the
        #  output node instead.
        # TODO: Maybe do not auto-collect any compositor node output file

        # Also collect any render output file nodes that are not 'registered'
        # yet
        if not bpy.context.scene.use_nodes:
            return

        tree = bpy.context.scene.node_tree
        for node in tree.nodes:
            if node.bl_idname != "CompositorNodeOutputFile":
                continue

            # If not is already imprinted and hence 'registered' we skip
            # it to avoid registering twice.
            project_name = self.create_context.get_current_project_name()
            folder_entity = self.create_context.get_current_folder_entity()
            task_entity = self.create_context.get_current_task_entity()
            task_name = self.create_context.get_current_task_name()
            host_name = "blender"
            variant = node.name
            product_name = self.get_product_name(
                project_name,
                folder_entity,
                task_entity,
                variant,
                host_name,
                project_entity=self.create_context.get_current_project_entity()
            )
            data = {
                "folderPath": folder_entity["path"],
                "task": task_name,
                "variant": variant,
                "productName": product_name,
                "productType": self.product_type,
                "creator_identifier": self.identifier,
                "id": AYON_CONTAINER_ID
            }
            instance = CreatedInstance(
                self.product_type, product_name, data, self
            )
            instance.transient_data["instance_node"] = node

            # Add instance to create context
            self._add_instance_to_context(instance)

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        return defs
