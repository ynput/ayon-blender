from typing import Dict, List, Optional

import bpy

from ayon_core.lib import BoolDef
from ayon_blender.api import plugin

from ayon_blender.api.plugin_load import (
    add_override,
    load_collection
)
from ayon_blender.api.pipeline import (
    containerise,
    metadata_update
)

class BlendLinkLoader(plugin.BlenderLoader):
    """Link assets from a .blend file."""

    product_types = {"*"}
    representations = {"blend"}

    label = "Link Blend"
    icon = "code-fork"
    color = "orange"

    options = [
        BoolDef(
            "addOverride",
            label="Add Override",
            default=False,
            tooltip="Add a library override for the loaded asset.",
        ),
        BoolDef(
            "group",
            label="Group",
            default=True,
            tooltip="Group the loaded asset in collections.",
        ),
    ]

    def process_asset(
        self,
        context: dict,
        name: str,
        namespace: Optional[str] = None,
        options: Optional[Dict] = None,
    ) -> Optional[List]:
        filepath = self.filepath_from_context(context)

        # Load a single Collection from the .blend file
        # TODO: Disallow loading same collection?
        loaded_collection = load_collection(
            filepath,
            link=True
        )

        scene = bpy.context.scene
        scene.collection.children.link(loaded_collection)

        options = options or dict()
        if options.get("addOverride", False):
            local_copy = add_override(loaded_collection)
            if local_copy:
                loaded_collection = local_copy

        container_collection = containerise(
            name=name,
            namespace=namespace,
            nodes=[loaded_collection],
            context=context,
            loader=self.__class__.__name__,
        )
        # TODO: Implement grouping of the loaded collection
        # if options.get("group", True):
        #     # Define names (for grouping)
        #     folder_name = context["folder"]["name"]
        #     product_name = context["product"]["name"]
        #     asset_name = plugin.prepare_scene_name(folder_name, product_name)
        #     unique_number = plugin.get_unique_number(folder_name, product_name)
        #     group_name = plugin.prepare_scene_name(
        #         folder_name, product_name, unique_number
        #     )
        #     add_asset_to_group(context["asset"], loaded_collection)

        # TODO: Store loader options for later use (e.g. on update)
        # Store the loader options on the container for later use if needed.
        metadata_update(container_collection, {"options": options})

        # Link the scene file
        with bpy.data.libraries.load(filepath,
                                     link=True) as (data_from, data_to):
            data_to.objects = data_from.objects

        # Add to the active collection
        for obj in data_to.objects:
            if obj is None:
                continue
            bpy.context.collection.objects.link(obj)

        return [loaded_collection]

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset."""
        repre = context["representation"]
        group_name = container["objectName"]
        collection = bpy.data.collections.get(group_name)
        library = self._get_library_from_collection(collection)

        # Update library filepath and reload it
        library.filepath = self.filepath_from_context(context)
        library.reload()

        # Update container metadata
        metadata_update(collection, {"representation": str(repre["id"])})

    def exec_remove(self, container: Dict) -> bool:
        """Remove existing container from the Blender scene."""
        group_name = container["objectName"]
        collection = bpy.data.collections.get(group_name)
        library = self._get_library_from_collection(collection)
        # TODO: Skip removal if used by other containers
        self.log.info("Deleting library: %s...", library.name_full)
        bpy.data.libraries.remove(library)
        # remove the container collection
        bpy.data.collections.remove(collection)

        return True

    def _get_library_from_collection(
            self, collection: bpy.types.Collection) -> bpy.types.Library:
        """Get the library from the collection."""
        for child in collection.children:
            if child.library or child.override_library:
                # No override library
                return child.library
            # With override library
            return child.override_library.reference.library
