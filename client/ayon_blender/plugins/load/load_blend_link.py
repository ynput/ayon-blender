import bpy
import os
from typing import Dict, List, Optional
from ayon_core.lib import BoolDef
from ayon_blender.api import plugin

from ayon_core.pipeline import AVALON_CONTAINER_ID
from ayon_blender.api.plugin_load import (
    add_override,
    load_collection
)
from ayon_blender.api.pipeline import (
    ls,
    AVALON_CONTAINERS,
    AVALON_PROPERTY,
    metadata_update,
    get_container_name
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
        folder_name = context["folder"]["name"]
        product_name = context["product"]["name"]

        unique_number = plugin.get_unique_number(folder_name, product_name)
        group_name = plugin.prepare_scene_name(
            folder_name, product_name, unique_number
        )
        namespace = namespace or f"{folder_name}_{unique_number}"
        container_name = get_container_name(
            name, namespace, context, suffix="CON"
        )
        loaded_collection = bpy.data.collections.get(container_name)
        scene_collection = bpy.context.scene.collection
        if loaded_collection and container_name in scene_collection.children:
            self.log.debug(f"Collection {container_name} already loaded.")
            return

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

        avalon_container = bpy.data.collections.get(AVALON_CONTAINERS)
        if not avalon_container:
            avalon_container = bpy.data.collections.new(name=AVALON_CONTAINERS)
            bpy.context.scene.collection.children.link(avalon_container)

        avalon_container.children.link(loaded_collection)
        data = {
            "schema": "openpype:container-2.0",
            "id": AVALON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
            "libpath": filepath,
            "objectName": group_name,
            "project_name": context["project"]["name"],
        }

        loaded_collection[AVALON_PROPERTY] = data
        # TODO: Store loader options for later use (e.g. on update)
        # Store the loader options on the container for later use if needed.

        collections = [
            coll for coll in bpy.data.collections
            if coll.name.startswith(f"{group_name}:")
        ]

        self[:] = collections

        return collections

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset. """
        repre = context["representation"]
        collection = container["node"]
        new_filepath = self.filepath_from_context(context)
        library = self._get_or_build_library_by_path(new_filepath)
        for node in collection.children:
            if node.library:
                node.library.filepath = library.filepath
                node.library.reload()
        # refresh UI
        bpy.context.view_layer.update()
        # Update container metadata
        updated_data = {
            "representation": str(repre["id"]),
            "libpath": new_filepath
        }
        metadata_update(collection, updated_data)

    def exec_remove(self, container: Dict) -> bool:
        """Remove existing container from the Blender scene."""
        collection = container["node"]
        library = self._get_library_from_collection(collection)
        if library:
            linked_to_coll = self._has_linked_to_existing_collections(library)
            if not linked_to_coll:
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
            if child.library:
                # No override library
                return child.library
            # With override library
            elif child.override_library and child.override_library.reference:
                return child.override_library.reference.library

        return None

    def _has_linked_to_existing_collections(
            self, library: bpy.types.Library) -> bool:
        """Check if any collection loaded by link
        scene loader linked to the same library.
        """
        existing_collections = [
            container["node"] for container in ls()
            if container["loader"] == str(
                self.__class__.__name__)
        ]
        match_count = list(
            coll for coll in existing_collections
            if self._get_library_from_collection(coll) == library
        )

        return len(match_count) > 1

    def _get_or_build_library_by_path(self, libpath: str) -> bpy.types.Library:
        """Get the library by filepath. If there is no any
        associated library to the path, the related library is loaded
        accordingly."""
        for library in bpy.data.libraries:
            if libpath == os.path.normpath(library.filepath):
                return library

        with bpy.data.libraries.load(libpath, link=True, relative=False) as (
            data_from,
            data_to
        ):
            if data_from.collections:
                data_to.collections = data_from.collections
            elif data_from.objects:
                data_to.objects = data_from.objects

        # Return the newly loaded library
        for library in bpy.data.libraries:
            if libpath == os.path.normpath(library.filepath):
                return library
