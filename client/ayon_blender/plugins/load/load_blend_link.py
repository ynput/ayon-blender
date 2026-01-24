import bpy
import os
from typing import Dict, List, Optional, Union
from ayon_core.lib import BoolDef
from ayon_blender.api import plugin

from ayon_blender.api.plugin_load import (
    add_override,
    load_collection,
    load_collection_through_libraries,
)
from ayon_blender.api.pipeline import (
    metadata_update,
    containerise,
    show_message
)


class BlendLinkLoader(plugin.BlenderLoader):
    """Link assets from a .blend file."""

    product_types = {
        "model", "camera", "rig",
        "layout", "blendScene",
        "animation", "workfile"
    }
    representations = {"blend"}

    label = "Link Blend"
    icon = "code-fork"
    color = "orange"

    instances_collections = False
    instance_object_data = False

    options = [
        BoolDef(
            "addOverride",
            label="Add Override",
            default=False,
            tooltip="Add a library override for the loaded asset.",
        ),
        BoolDef(
            "instances_collections",
            label="Instances Collection",
            default=False,
            tooltip=("Create instances for collections, "
                     "rather than adding them directly to the scene."),
        ),
        BoolDef(
            "instance_object_data",
            label="Instance Object Data",
            default=False,
            tooltip=("Create instances for object data which "
                     "are not referenced by any objects"),
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
        product_type = context["product"]["productType"]

        unique_number = plugin.get_unique_number(folder_name, product_name)
        group_name = plugin.prepare_scene_name(
            folder_name, product_name, unique_number
        )
        namespace = namespace or f"{folder_name}_{unique_number}"
        instances_collections = options.get(
            "instances_collections", self.instances_collections
        )
        instance_object_data = options.get(
            "instance_object_data", self.instance_object_data
        )
        # TODO: we need to discuss the possible solutions for aligning
        # the publishing workflow with collection
        if product_type in {"rig", "model", "animation", "camera"}:
            loaded_collection = load_collection_through_libraries(
                filepath,
                link=True,
                group_name=group_name
            )
            if loaded_collection.name in bpy.context.scene.collection.children:
                show_message(f"Collection {loaded_collection.name} already linked",
                    f"Collection '{loaded_collection.name}' is already linked to the scene."
                )
                return
        else:
            loaded_collection = load_collection(
                filepath,
                link=True,
                group_name=group_name,
                instances_collections=instances_collections,
                instance_object_data=instance_object_data
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
        if collection.children:
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
        if collection.children:
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
                return child.library
            # With override library
            elif child.override_library and child.override_library.reference:
                return child.override_library.reference.library

        for child in collection.objects:
            if child.library:
                return child.library
            # With override library
            elif child.override_library and child.override_library.reference:
                return child.override_library.reference.library

        return None
