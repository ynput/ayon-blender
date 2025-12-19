"""Create render."""
import os
import re

import bpy
from typing import Optional

from ayon_core.lib import BoolDef
from ayon_core.pipeline.create import CreatedInstance
from ayon_blender.api import plugin, lib, render_lib

BLENDER_VERSION = lib.get_blender_version()


def clean_name(name: str) -> str:
    """Ensure variant name is valid, e.g. strip spaces from name"""
    # Entity name regex taken from server code which also applies to
    # product names (which usually
    name_regex = r"^[a-zA-Z0-9_]([a-zA-Z0-9_\.\-]*[a-zA-Z0-9_])?$"

    # Replace space with underscore
    clean = name.replace(" ", "")
    # Strip out any remaining invalid characters
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "", clean)
    # Ensure start and end characters are not a dot or dash
    clean = clean.strip(".-")
    # Ensure name is at least 1 character long
    if not clean:
        # Fallback to a default name
        clean = "Main"

    if not re.match(name_regex, clean):
        raise ValueError(f"Failed to create valid name for {name}")
    return clean


class CreateRender(plugin.BlenderCreator):
    """Create render from Compositor File Output node"""

    identifier = "io.ayon.creators.blender.render"
    label = "Render"
    description = __doc__
    product_type = "render"
    product_base_type = "render"
    icon = "eye"

    def _find_compositor_node_from_create_render_setup(self) -> Optional["bpy.types.CompositorNodeOutputFile"]:
        tree = lib.get_scene_node_tree()
        for node in tree.nodes:
            if (
                    node.bl_idname == "CompositorNodeOutputFile"
                    and node.name == "AYON File Output"
            ):
                return node
        return None

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        tree = lib.get_scene_node_tree(ensure_exists=True)

        variant: str = instance_data.get("variant", self.default_variant)

        if pre_create_data.get("create_render_setup", False):
            # TODO: Prepare rendering setup should always generate a new
            #  setup, and return the relevant compositor node instead of
            #  guessing afterwards
            node = render_lib.prepare_rendering(variant_name=variant)
        else:
            # Create a Compositor node
            node: bpy.types.CompositorNodeOutputFile = tree.nodes.new(
                "CompositorNodeOutputFile"
            )
            project_settings = (
                self.create_context.get_current_project_settings()
            )
            base_path = render_lib.get_base_render_output_path(
                variant_name=variant,
                # For now enforce multi-exr here since we are not connecting
                # any inputs and it at least ensures a full path is set.
                multi_exr=True,
                project_settings=project_settings,
            )
            node.format.file_format = "OPEN_EXR_MULTILAYER"
            if BLENDER_VERSION >= (5, 0, 0):
                directory, filename = os.path.split(base_path)
                node.directory = directory
                node.file_name = filename
            else:
                node.base_path = base_path

        node.name = variant
        node.label = variant

        self.set_instance_data(product_name, instance_data)
        instance = CreatedInstance(
            self.product_type, product_name, instance_data, self
        )
        instance.transient_data["instance_node"] = node
        self._add_instance_to_context(instance)

        self.imprint(node, instance_data)

        return instance

    def collect_instances(self):
        node_tree = lib.get_scene_node_tree()
        if not node_tree:
            # Blender 5.0 may not have created and set a compositor group
            return

        super().collect_instances()

        # TODO: Collect all Compositor nodes - even those that are not
        #   imprinted with any data.
        collected_nodes = {
            created_instance.transient_data.get("instance_node")
            for created_instance in self.create_context.instances
        }
        collected_nodes.discard(None)

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
            # Find the related compositor node
            # TODO: Find the actual relevant compositor node instead of just
            #  any
            comp_node = self._find_compositor_node_from_create_render_setup()
            if not comp_node:
                raise RuntimeError("No compositor node found")

            instance.transient_data["instance_node"] = comp_node
            self.imprint(comp_node, instance.data_to_store())

            # Delete the original object
            bpy.data.collections.remove(node)

        # Collect all remaining compositor output nodes
        unregistered_output_nodes = [
            node for node in node_tree.nodes
            if node.bl_idname == "CompositorNodeOutputFile"
            and node not in collected_nodes
        ]
        if not unregistered_output_nodes:
            return

        project_name = self.create_context.get_current_project_name()
        project_entity = self.create_context.get_current_project_entity()
        folder_entity = self.create_context.get_current_folder_entity()
        task_entity = self.create_context.get_current_task_entity()
        for node in unregistered_output_nodes:
            self.log.info("Found unregistered render output node: %s",
                          node.name)
            variant = clean_name(node.name)
            product_name = self.get_product_name(
                project_name=project_name,
                project_entity=project_entity,
                folder_entity=folder_entity,
                task_entity=task_entity,
                variant=variant,
                host_name=self.create_context.host_name,
            )
            instance_data = self.read(node)
            instance_data.update({
                "folderPath": folder_entity["path"],
                "task": task_entity["name"],
                "productName": product_name,
                "variant": variant,
            })

            instance = CreatedInstance(
                self.product_type,
                product_name,
                data=instance_data,
                creator=self,
                transient_data={
                    "instance_node": node
                }
            )
            self._add_instance_to_context(instance)

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        defs.extend([
            BoolDef("review",
                    label="Review",
                    tooltip="Mark as reviewable",
                    default=True
            )
        ])
        return defs

    def get_pre_create_attr_defs(self):
        return [
            BoolDef(
                "create_render_setup",
                label="Create Render Setup",
                default=False,
                tooltip="Create Render Setup",
            ),

        ]

    def imprint(self, node: bpy.types.CompositorNodeOutputFile, data: dict):
        # Use the node `mute` state to define the active state of the instance.
        active = data.pop("active", True)
        node.mute = not active
        super().imprint(node, data)

    def read(self, node: bpy.types.CompositorNodeOutputFile) -> dict:
        # Read the active state from the node `mute` state.
        data = super().read(node)

        # On super().collect_instances() it may collect legacy render instances
        # that are not Compositor nodes but Collection objects.
        if isinstance(node, bpy.types.CompositorNodeOutputFile):
            data["active"] = not node.mute

        return data
