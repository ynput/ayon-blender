import bpy
import os
import hashlib
import shutil
from typing import Dict, List, Optional, Union
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
        ),
        BoolDef(
            "use_arbitrary_loc_for_library",
            label="Use Arbitrary Location for Library",
            default=False,
            tooltip="Store the library in arbitrary location"
                    "Use with caution when blend file is big.",
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
        use_arbitrary_loc = options.get("use_arbitrary_loc_for_library")
        if use_arbitrary_loc:
            filepath = self.use_arbitrary_location_for_library(filepath, group_name)
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
            "arbitrary_location_for_library": use_arbitrary_loc
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
        # currently updating version only applicable to the single asset
        # it does not support for versioning in multiple assets
        library = (
            self._get_library_from_collection(collection)
            or self._get_library_by_prev_libpath(container)
        )
        filepath = self.filepath_from_context(context)

        # Update library filepath and reload it if there is library
        if library:
            self.update_library_filepath(
                library, filepath,
                container.get("arbitrary_location_for_library", False)
            )

        # refresh UI
        bpy.context.view_layer.update()
        # Update container metadata
        updated_data = {
            "representation": str(repre["id"]),
            "lib_path": filepath
        }

        # Update container metadata
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
            self, collection: bpy.types.Collection) -> Union[bpy.types.Library, None]:
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

    def _get_library_by_prev_libpath(
            self, container: Dict) -> Union[bpy.types.Library, None]:
        """Get the library by filename."""
        lib_path = container["libpath"]
        for library in bpy.data.libraries:
            if lib_path == library.filepath:
                return library

    def use_arbitrary_location_for_library(self, filepath: str, group_name: str) -> str:
        """Use arbitrary location for library to store the linked libraries
        Not recommend for extremely giant .blend files.

        Args:
            filepath (str): filepath
            group_name (str): group name

        Returns:
            str: destination path
        """
        group_name = group_name.encode("utf-8")
        unique_id = hashlib.sha512(group_name).hexdigest()
        arbitrary_directory = os.path.join(
            os.getenv("AYON_WORKDIR"), ".linked_folder", unique_id
        )
        os.makedirs(arbitrary_directory, exist_ok=True)
        filename = os.path.basename(filepath)
        dst_filepath = os.path.join(arbitrary_directory, filename)
        shutil.copy(filepath, dst_filepath)

        return dst_filepath

    def update_library_filepath(
            self, library: bpy.types.Library, filepath: str,
            use_arbitrary: bool = False
        ):
        """Update library filepath when updating container

        Args:
            library (bpy.types.Library): library
            filepath (str): filepath
            use_arbitrary (bool, optional): use arbitrary location. Defaults to False.
        """
        filename = os.path.basename(filepath)
        library.name = filename
        if not use_arbitrary:
            library.filepath = filepath
            library.reload()
        else:
            current_libpath = library.filepath
            lib_directory = os.path.dirname(current_libpath)
            updated_libpath = os.path.join(lib_directory, filename)
            shutil.copy(filepath, updated_libpath)
            library.filepath = updated_libpath
            library.reload()
            os.remove(current_libpath)
