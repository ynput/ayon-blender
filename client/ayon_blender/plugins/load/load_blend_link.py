from typing import Dict, List, Optional
import os
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
        )
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
        scene_collection = bpy.context.scene.collection
        if loaded_collection and container_name in scene_collection.children:
            self.log.debug(f"Collection {container_name} already loaded.")
            return
        folder_name = context["folder"]["name"]
        product_name = context["product"]["name"]

        unique_number = plugin.get_unique_number(folder_name, product_name)
        group_name = plugin.prepare_scene_name(
            folder_name, product_name, unique_number
        )
        namespace = namespace or f"{folder_name}_{unique_number}"
        loaded_collection = load_collection(
            filepath,
            link=True,
            group_name=group_name
        )

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
        # TODO: Store loader options for later use (e.g. on update)
        # Store the loader options on the container for later use if needed.
        extra_data =  {
            "options": options,
            "lib_name": os.path.basename(filepath)
        }
        metadata_update(container_collection, extra_data)

        return (container_collection, loaded_collection)

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset."""
        repre = context["representation"]
        collection = container["node"]
        new_filepath = self.filepath_from_context(context)
        new_filename = os.path.basename(new_filepath)
        # Update library filepath and reload it
        library = (
            self._get_library_from_collection(collection)
            or self._get_library_by_name(container)
        )
        library.name = new_filename
        library.filepath = new_filepath
        library.reload()

        # refresh UI
        bpy.context.view_layer.update()
        # Update container metadata
        updated_data = {
            "representation": str(repre["id"]),
            "lib_name": new_filename
        }
        metadata_update(collection, updated_data)

    def exec_remove(self, container: Dict) -> bool:
        """Remove existing container from the Blender scene."""
        collection = container["node"]
        library = self._get_library_from_collection(collection)
        if library:
            bpy.data.libraries.remove(library)
        else:
            # Ensure the collection is linked to the scene's master collection
            scene_collection = bpy.context.scene.collection
            for col in collection.children:
                scene_collection.children.unlink(col)
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

    def _get_library_by_name(self, container: Dict) -> bpy.types.Library:
        """Get the library by filename."""
        lib_name = container["lib_name"]
        for library in bpy.data.libraries:
            if lib_name in library.name:
                return library
