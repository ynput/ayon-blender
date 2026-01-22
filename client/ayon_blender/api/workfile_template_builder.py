"""Blender workfile template builder implementation"""
import bpy

import itertools
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.workfile.workfile_template_builder import (
    TemplateAlreadyImported,
    AbstractTemplateBuilder,
    PlaceholderPlugin,
    PlaceholderItem,
)
from ayon_core.tools.workfile_template_build import (
    WorkfileBuildPlaceholderDialog,
)

from .constants import AYON_INSTANCES
from .pipeline import get_ayon_property
from .lib import (
    get_scene_node_tree,
    get_selected_collections,
    imprint,
    update_content_on_context_change
)

from pathlib import Path


PLACEHOLDER_SET = "PLACEHOLDERS_SET"


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
        if bpy.data.collections.get(PLACEHOLDER_SET):
            raise TemplateAlreadyImported((
                "Build template already loaded\n"
                "Clean scene if needed (File > New Scene)"
            ))

        placeholder_collection = bpy.data.collections.new(PLACEHOLDER_SET)
        bpy.context.scene.collection.children.link(placeholder_collection)
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
        update_content_on_context_change()
        return True

class BlenderPlaceholderPlugin(PlaceholderPlugin):
    """Base Placeholder Plugin for Blender with one unified cache.

    Creates a locator as placeholder node, which during populate provide
    all of its attributes defined on the locator's transform in
    `placeholder.data` and where `placeholder.scene_identifier` is the
    full path to the node.

    Inherited classes must still implement `populate_placeholder`

    """

    use_selection_as_parent = True
    item_class = PlaceholderItem

    def _create_placeholder_name(self, placeholder_data):
        return self.identifier.replace(".", "_")

    def _collect_scene_placeholders(self):
        nodes_by_identifier = self.builder.get_shared_populate_data(
            "placeholder_nodes"
        )
        if nodes_by_identifier is None:
            # Cache placeholder data to shared data
            nodes = [
                node for node in bpy.data.collections
                if get_ayon_property(node)
            ]

            nodes_by_identifier = {}
            for node in nodes:
                ayon_prop = get_ayon_property(node)
                identifier = ayon_prop.get("plugin_identifier")
                if not identifier:
                    continue
                nodes_by_identifier.setdefault(identifier, []).append(node)

            # Set the cache
            self.builder.set_shared_populate_data(
                "placeholder_nodes", nodes_by_identifier
            )
        return nodes_by_identifier

    def create_placeholder(self, placeholder_data):

        parent_object = None
        if self.use_selection_as_parent:
            selection = get_selected_collections()
            if len(selection) > 1:
                raise ValueError(
                    "More than one collection is selected. "
                    "Please select only one to define the parent."
                )
            parent_object = selection[0] if selection else None

        placeholder_data["plugin_identifier"] = self.identifier
        placeholder_name = self._create_placeholder_name(placeholder_data)

        placeholder = bpy.data.collections.new(placeholder_name)
        if parent_object:
            parent_object.children.link(placeholder)
            imprinted_placeholder = parent_object
        else:
            bpy.context.scene.collection.children.link(placeholder)
            imprinted_placeholder = placeholder

        imprint(imprinted_placeholder, placeholder_data)

    def update_placeholder(self, placeholder_item, placeholder_data):
        node_name = placeholder_item.scene_identifier

        changed_values = {}
        for key, value in placeholder_data.items():
            if value != placeholder_item.data.get(key):
                changed_values[key] = value

        target_collection = bpy.data.collections.get(node_name)
        target_property = get_ayon_property(target_collection)
        # Delete attributes to ensure we imprint new data with correct type
        for key in changed_values.keys():
            placeholder_item.data[key] = value
            if key in target_property:
                    target_property.pop(key, None)

        self.imprint(node_name, changed_values)

    def collect_placeholders(self):
        placeholders = []
        nodes_by_identifier = self._collect_scene_placeholders()
        for node in nodes_by_identifier.get(self.identifier, []):
            # TODO do data validations and maybe upgrades if they are invalid
            placeholder_data = get_ayon_property(node)
            placeholders.append(
                self.item_class(scene_identifier=node,
                                data=placeholder_data,
                                plugin=self)
            )

        return placeholders

    def post_placeholder_process(self, placeholder, failed):
        """Cleanup placeholder after load of its corresponding representations.

        Hide placeholder, add them to placeholder set.
        Used only by PlaceholderCreateMixin and PlaceholderLoadMixin

        Args:
            placeholder (PlaceholderItem): Item which was just used to load
                representation.
            failed (bool): Loading of representation failed.
        """
        # Hide placeholder and add them to placeholder set
        node = placeholder.scene_identifier

        # If we just populate the placeholders from current scene, the
        # placeholder set will not be created so account for that.
        placeholder_set = bpy.data.collections.get(PLACEHOLDER_SET)
        if placeholder_set:
            placeholder_set = bpy.data.collections.new(name=PLACEHOLDER_SET)
        placeholder_set.children = node

    def delete_placeholder(self, placeholder):
        """Remove placeholder if building was successful

        Used only by PlaceholderCreateMixin and PlaceholderLoadMixin.
        """
        node = placeholder.scene_identifier
        node_to_removed = bpy.data.collections.get(node)
        if node_to_removed:
            bpy.data.collections.remove(node_to_removed)

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

        imprint(obj_or_col, {"folderPath": folder_path})


def create_first_worfile_from_template(*args) -> None:
    """Create the first workfile from template for Blender."""
    builder = BlenderTemplateBuilder(registered_host())
    builder.build_template(workfile_creation_enabled=True)


def build_workfile_template(*args) -> None:
    """Build the workfile template."""
    builder = BlenderTemplateBuilder(registered_host())
    builder.build_template()


# def update_workfile_template(*args) -> None:
#     """Update the workfile template."""
#     builder = BlenderTemplateBuilder(registered_host())
#     builder.rebuild_template()


def create_placeholder(*args, **kwargs):
    """Create Workfile Placeholder for Blender."""
    host = registered_host()
    builder = BlenderTemplateBuilder(host)
    parent = kwargs.get("parent")
    window = WorkfileBuildPlaceholderDialog(host, builder,
                                            parent=parent)
    window.show()
    return window


def update_placeholder(*args, **kwargs):
    """Update Workfile Placeholder for Blender."""
    host = registered_host()
    builder = BlenderTemplateBuilder(host)
    placeholder_items_by_id = {
        placeholder_item.scene_identifier: placeholder_item
        for placeholder_item in builder.get_placeholders()
    }
    placeholder_items = []
    for node in get_selected_collections():
        if node.name in placeholder_items_by_id:
            placeholder_items.append(placeholder_items_by_id[node.name])

    # TODO show UI at least
    if len(placeholder_items) == 0:
        raise ValueError("No node selected")

    if len(placeholder_items) > 1:
        raise ValueError("Too many selected nodes")

    placeholder_item = placeholder_items[0]
    parent = kwargs.get("parent")
    window = WorkfileBuildPlaceholderDialog(host, builder,
                                            parent=parent)
    window.set_update_mode(placeholder_item)
    window.exec_()
    return window
