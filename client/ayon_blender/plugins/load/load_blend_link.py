import bpy
from typing import Dict, List, Optional, Union
from ayon_core.lib import BoolDef
from ayon_blender.api import plugin

from ayon_core.pipeline import AYON_CONTAINER_ID
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
        library = self._get_library_from_collection(loaded_collection)
        avalon_container.children.link(loaded_collection)
        data = {
            "schema": "ayon:container-3.0",
            "id": AYON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
            "libpath": filepath,
            "project_name": context["project"]["name"],
            "loaded_collection": loaded_collection
        }

        library[AVALON_PROPERTY] = data
        library.name = container_name
        # TODO: Store loader options for later use (e.g. on update)
        # Store the loader options on the container for later use if needed.
        return [library]

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset. """
        repre = context["representation"]
        library = container["node"]
        # currently updating version only applicable to the single asset
        # it does not support for versioning in multiple assets
        filepath = self.filepath_from_context(context)
        # Update library filepath and reload it if there is library
        library.filepath = filepath
        library.reload()

        # refresh UI
        bpy.context.view_layer.update()
        # Update container metadata
        metadata_update(library, {"representation": str(repre["id"])})

    def exec_remove(self, container: Dict) -> bool:
        """Remove existing container from the Blender scene."""
        library = container["node"]
        collection = container["loaded_collection"]
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
            container["loaded_collection"] for container in ls()
            if container["loader"] == str(
                self.__class__.__name__)
        ]
        match_count = list(
            coll for coll in existing_collections
            if self._get_library_from_collection(coll) == library
        )

        return len(match_count) > 1
