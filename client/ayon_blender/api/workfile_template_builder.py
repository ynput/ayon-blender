"""Blender workfile template builder implementation"""
import bpy

import itertools
from ayon_core.pipeline import (
    registered_host,
    get_current_folder_path
)
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
)
from .constants import AYON_INSTANCES
from .pipeline import (
    get_ayon_property,
    metadata_update
)
from .lib import get_scene_node_tree

from pathlib import Path


class BlenderTemplateBuilder(AbstractTemplateBuilder):
    """Concrete implementation of AbstractTemplateBuilder for Blender"""
    def import_template(self, path):
        """Import template into current scene.
        Block if a template is already loaded.

        Args:
            path (str): A path to current template (usually given by
            get_template_preset implementation)

        Returns:
            bool: Whether the template was successfully imported or not
        """
        filepath = Path(path)
        if not filepath.exists():
            return False

        with bpy.data.libraries.load(filepath.as_posix()) as (data_src, data_dst):
            data_dst.collections = data_src.collections
            data_dst.objects = data_src.objects

        for target_object in data_dst.objects:
            bpy.context.scene.collection.objects.link(target_object)
        for target_collection in data_dst.collections:
            bpy.context.scene.collection.children.link(target_collection)

        # update imported sets information
        folder_path = get_current_folder_path()
        set_folder_path_for_ayon_instances(folder_path)
        return True

def set_folder_path_for_ayon_instances(folder_path: str) -> None:
    """Set the folder path for AYON instances in the Blender scene.

    Args:
        folder_path (str): The folder path to set for AYON instances.
    """
    ayon_instances = bpy.data.collections.get(AYON_INSTANCES)
    ayon_instance_objs = (
        ayon_instances.objects if ayon_instances else []
    )

    # Consider any node tree objects as well
    node_tree_objects = []
    node_tree = get_scene_node_tree()
    if node_tree:
        node_tree_objects = node_tree.nodes

    for obj_or_col in itertools.chain(
            ayon_instance_objs,
            bpy.data.collections,
            node_tree_objects
    ):
        ayon_prop = get_ayon_property(obj_or_col)
        if not ayon_prop:
            continue
        if not ayon_prop.get("folderPath"):
            continue
        metadata_update(obj_or_col, {"folderPath": folder_path})

def build_workfile_template(*args) -> None:
    """Build the workfile template."""
    builder = BlenderTemplateBuilder(registered_host())
    builder.build_template()


def update_workfile_template(*args) -> None:
    """Update the workfile template."""
    builder = BlenderTemplateBuilder(registered_host())
    builder.rebuild_template()
