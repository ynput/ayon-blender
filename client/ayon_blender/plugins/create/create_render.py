"""Create render."""
import bpy
from typing import Optional

from ayon_core.pipeline.create import CreatedInstance
from ayon_blender.api import plugin, lib, prepare_rendering


class CreateRender(plugin.BlenderCreator):
    """Create render instance."""

    identifier = "io.openpype.creators.blender.render"
    label = "Render"
    product_type = "render"
    icon = "eye"

    # TODO: Convert legacy instances to new style instances by finding the
    #  relevant file output node and moving the imprinted data there.

    def _find_existing_compositor_output_node(self) -> Optional["bpy.types.CompositorNodeOutputFile"]:
        if not bpy.context.scene.use_nodes:
            return None

        # TODO: If user has a selected compositor node, prefer that one
        # TODO: What to do if multiples exist?
        tree = bpy.context.scene.node_tree
        for node in tree.nodes:
            if node.bl_idname == "CompositorNodeOutputFile":
                return node

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        # This behavior is somewhat similar to `ayon-maya` for rendering.
        # If no render setup is created yet, we create it. If there is, then
        # we assume the existing one is what we want to maintain and create
        # a registry for the existing setup.
        # TODO: pre-connect any existing passes according to settings.
        # TODO: Do not override scene render engine (unless explicitly enabled)
        # TODO: Should we allow multiple render setups in a single scene?
        node = self._find_existing_compositor_output_node()
        if not node:
            # Create render setup
            variant = instance_data.get("variant", self.default_variant)

            prepare_rendering(name=variant)
            node = self._find_existing_compositor_output_node()

            # Force enable compositor
            bpy.context.scene.use_nodes = True

            node.name = variant
            node.label = variant

        self.set_instance_data(product_name, instance_data)
        instance = CreatedInstance(
            self.product_type, product_name, instance_data, self
        )
        instance.transient_data["instance_node"] = node
        self._add_instance_to_context(instance)

        lib.imprint(node, instance_data)

        return node

    def collect_instances(self):
        super().collect_instances()

        # Convert legacy instances that did not yet imprint on the
        # compositor node itself
        for instance in self.create_context.instances:
            instance: CreatedInstance

            # Ignore instances from other creators
            if instance.creator_identifier != self.identifier:
                continue

            # Check if node type is the old object type
            node = instance.transient_data["instance_node"]

            if not isinstance(node, bpy.types.Collection):
                # Already new-style node
                continue

            self.log.info(f"Converting legacy render instance: {node}")

            # TODO: Confirm the 'legacy' instance is actually a Collection

            # Find the related compositor node
            # TODO: Find the actual relevant compositor node instead of just
            #  any
            comp_node = self._find_existing_compositor_output_node()
            if not comp_node:
                raise RuntimeError("No compositor node found")

            instance.transient_data["instance_node"] = comp_node
            lib.imprint(comp_node, instance.data_to_store())

            # Delete the original object
            bpy.data.collections.remove(node)

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        return defs
