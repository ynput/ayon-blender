import os
import json
import contextlib


import bpy
import pyblish.api

from ayon_core.pipeline import publish
from ayon_blender.api import plugin
from ayon_blender.api.pipeline import ls
from ayon_blender.api.lib import (
    strip_container_data,
    strip_instance_data,
    strip_namespace,
    packed_images,
    make_material_image_paths_absolute,
    get_material_assignments,
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
    families = ["model", "camera", "rig", "layout", "blendScene"]
    optional = True

    # From settings
    compress = False
    pack_textures = True

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

        data_blocks = self.add_datablock(instance)
        asset_group = instance.data["transientData"]["instance_node"]
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
            stack.enter_context(strip_instance_data(asset_group))
            stack.enter_context(strip_namespace(containers))
            if self.pack_textures:
                stack.enter_context(
                    packed_images(data_blocks, logger=self.log)
                )
            # make sure all texture files are absolute paths
            if instance.data["productBaseType"] == "look":
                stack.enter_context(make_material_image_paths_absolute(data_blocks))

            self.log.debug("Datablocks: %s", data_blocks)
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

    def add_datablock(self, instance: pyblish.api.Instance) -> set:
        """Add a data block to the blend file.

        Args:
            instance (pyblish.api.Instance): The instance to add.

        Returns:
            set: A set of data blocks added.
        """
        return set(instance)

class ExtractBlendAction(ExtractBlend):
    """Extract a blend file from the current scene.
    """
    families = ["action"]
    label = "Extract Blend (Action)"
    optional = False
    # From settings
    compress = False

    def add_datablock(self, instance: pyblish.api.Instance) -> set:
        """Add a data block to the blend file.

        Args:
            instance (pyblish.api.Instance): The instance to add.

        Returns:
            set: A set of data blocks added.
        """
        return {
            action for action in bpy.data.actions
            if action.name == instance.data["productName"]
        }


class ExtractBlendLook(ExtractBlend):
    """Extract the look materials to a .blend file.

    Alongside the .blend file a .json file is extracted that records which
    material is assigned to which object (material slot), so the loader can
    re-assign the materials to objects with matching names.
    """
    families = ["look"]
    label = "Extract Blend (Look)"
    optional = False
    # From settings
    compress = False

    def process(self, instance):
        # Extract the materials to a .blend file
        super().process(instance)

        # Extract the material assignments to a .json file
        relationships = get_material_assignments(instance)
        if not relationships:
            self.log.warning(
                "No material assignments found for the objects in instance"
                " '%s'.", instance.name
            )

        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        filename = f"{folder_name}_{product_name}.json"
        filepath = os.path.join(stagingdir, filename)

        self.log.debug("Extracting material assignments to: %s", filepath)
        with open(filepath, "w") as f:
            json.dump({"relationships": relationships}, f, indent=4)

        instance.data["representations"].append({
            "name": "json",
            "ext": "json",
            "files": filename,
            "stagingDir": stagingdir,
        })

    def add_datablock(self, instance: pyblish.api.Instance) -> set:
        """Add the material data block to the blend file.
        The datablock needs to be exported along with its linked objects
        to preserve the material's node tree and texture links.

        Both the materials of the object data and the materials of the
        object's material slots are included, so materials linked to the
        object (instead of its data) are exported as well.

        Args:
            instance (pyblish.api.Instance): The instance to add.

        Returns:
            set: A set of data blocks added.
        """
        datablock_to_be_exported = set()
        for obj in instance:
            if not isinstance(obj, bpy.types.Object):
                continue
            if not hasattr(obj.data, "materials"):
                continue
            datablock_to_be_exported.update(obj.data.materials)
            datablock_to_be_exported.update(
                slot.material for slot in obj.material_slots
            )
        # Ignore empty material slots
        datablock_to_be_exported.discard(None)
        return datablock_to_be_exported
