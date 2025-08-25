import bpy
import os
from typing import Dict, List, Optional, Union
from ayon_core.lib import BoolDef
from ayon_blender.api import plugin

from ayon_blender.api.plugin_load import (
    add_override,
    load_collection
)
from ayon_blender.api.pipeline import (
    metadata_update,
    get_container_name,
    containerise,
    show_message
)


class BlendLinkLoader(plugin.BlenderLoader):
    """Link assets from a .blend file."""

    product_types = {"model", "camera", "rig",
        "action", "layout", "blendScene", "animation"}
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

        if loaded_collection and group_name in scene_collection.children:

            message = (
                f"Collection {group_name} already loaded, "
                f"instance to {group_name} is created instead of "
                "linking new collection"
            )
            show_message(f"Collection {group_name} already loaded", message)
            instance = bpy.data.objects.new(name=group_name, object_data=None)
            instance.instance_type = 'COLLECTION'
            instance.instance_collection = loaded_collection
            # Link the instance to the active scene
            bpy.context.scene.collection.objects.link(instance)
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

        container_collection = containerise(
            name=name,
            namespace=namespace,
            nodes=[loaded_collection],
            context=context,
            loader=self.__class__.__name__,
        )

        return container_collection

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset. """
        repre = context["representation"]
        collection = container["node"]
        library = self._get_library_from_collection(collection.children[0])
        filepath = self.filepath_from_context(context)
        filename = os.path.basename(filepath)
        if library:
            library.name = filename
            library.filepath = filepath
            library.reload()
        # refresh UI
        bpy.context.view_layer.update()

        # Update container metadata
        metadata_update(
            collection, {"representation": str(repre["id"])}
        )

    def exec_remove(self, container: Dict) -> bool:
        """Remove existing container from the Blender scene."""

        collection = container["node"]
        library = self._get_library_from_collection(collection.children[0])
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
