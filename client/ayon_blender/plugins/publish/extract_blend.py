import os
import contextlib

import bpy

from ayon_core.pipeline import publish
from ayon_blender.api import plugin
from ayon_blender.api.pipeline import ls
from ayon_blender.api.lib import (
    strip_container_data,
    strip_namespace
)


@contextlib.contextmanager
def link_to_collection(collection, objects):
    """Link objects to a collection during context"""
    unlink_after = []
    try:
        for obj in objects:
            if not isinstance(obj, bpy.types.Object):
                continue
            if collection not in obj.users_collection:
                unlink_after.append(obj)
                collection.objects.link(obj)
        yield
    finally:
        for obj in unlink_after:
            collection.objects.unlink(obj)


class ExtractBlend(
    plugin.BlenderExtractor, publish.OptionalPyblishPluginMixin
):
    """Extract a blend file."""

    label = "Extract Blend"
    hosts = ["blender"]
    families = ["model", "camera", "rig", "action", "layout", "blendScene"]
    optional = True

    # From settings
    compress = False

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Define extract output file path

        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        instance_name = f"{folder_name}_{product_name}"
        filename = f"{instance_name}.blend"
        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.debug("Performing extraction..")

        data_blocks = set()

        for data in instance:
            data_blocks.add(data)
            # Pack used images in the blend files.
            if not (
                isinstance(data, bpy.types.Object) and data.type == 'MESH'
            ):
                continue
            for material_slot in data.material_slots:
                mat = material_slot.material
                if not (mat and mat.use_nodes):
                    continue
                tree = mat.node_tree
                if tree.type != 'SHADER':
                    continue
                for node in tree.nodes:
                    if node.bl_idname != 'ShaderNodeTexImage':
                        continue
                    # Check if image is not packed already
                    # and pack it if not.
                    if node.image and node.image.packed_file is None:
                        node.image.pack()

        containers = list(ls())
        with contextlib.ExitStack() as stack:
            # If the instance node is a Collection, we want to enforce the
            # full child hierarchies to be included in the written collections.
            instance_node = instance.data["transientData"]["instance_node"]
            if isinstance(instance_node, bpy.types.Collection):
                # We only link children nodes to the 'parent' collection it is
                # in so that the full children hierarchy is preserved for the
                # main collection, and all its child collections.
                collections = [instance_node]
                collections.extend(instance_node.children_recursive)
                for collection in set(collections):
                    missing_child_hierarchy = set()
                    for obj in collection.objects:
                        for child in obj.children_recursive:
                            if collection not in child.users_collection:
                                missing_child_hierarchy.add(child)

                    if missing_child_hierarchy:
                        stack.enter_context(link_to_collection(
                            collection, list(missing_child_hierarchy)))

            stack.enter_context(strip_container_data(containers))
            stack.enter_context(strip_namespace(containers))
            bpy.data.libraries.write(
                filepath, data_blocks, compress=self.compress
            )

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'blend',
            'ext': 'blend',
            'files': filename,
            "stagingDir": stagingdir,
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extracted instance '%s' to: %s",
                       instance.name, representation)
