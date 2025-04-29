from typing import Dict, List, Optional

import bpy

from ayon_core.lib import BoolDef
from ayon_blender.api import plugin

from ayon_blender.api.plugin_load import (
    add_override,
    load_collection,
    add_asset_to_group
)
from ayon_blender.api.pipeline import (
    containerise,
    metadata_update
)
from ayon_blender.api.lib import get_container_name


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
            default=False,
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
        container_name = get_container_name(
            name, namespace, context, suffix="CON"
        )
        loaded_collection = bpy.data.collections.get(container_name)
        if loaded_collection:
            self.log.debug(f"Collection {container_name} already loaded.")
            return

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
        if options.get("group", True):
            add_asset_to_group(context["folder"], loaded_collection)
        # TODO: Store loader options for later use (e.g. on update)
        # Store the loader options on the container for later use if needed.
        metadata_update(container_collection, {"options": options})

        return (container_collection, loaded_collection)

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset."""
        repre = context["representation"]
        collection = container["node"]
        library = self._get_library_from_collection(collection)

        # Update library filepath and reload it
        library.filepath = self.filepath_from_context(context)
        library.reload()
        # refresh UI refresh
        bpy.context.view_layer.update()
        # Update container metadata
        metadata_update(collection, {"representation": str(repre["id"])})

    def exec_remove(self, container: Dict) -> bool:
        """Remove existing container from the Blender scene."""
        collection = container["node"]
        library = self._get_library_from_collection(collection)

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

        return None
