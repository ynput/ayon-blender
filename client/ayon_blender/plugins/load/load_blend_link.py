import bpy
import os
from typing import Dict, List, Optional, Union
from ayon_core.lib import BoolDef
from ayon_blender.api import plugin

from ayon_blender.api.plugin_load import (
    add_override,
    link_collection,
    load_collection,
    find_collection_by_name,
    find_objects_by_name,
)
from ayon_blender.api.pipeline import (
    metadata_update,
    containerise,
    get_container_name,
    show_message
)


class BlendLinkLoader(plugin.BlenderLoader):
    """Link assets from a .blend file."""

    product_types = {
        "model", "camera", "rig",
        "layout", "animation", "workfile"
    }
    representations = {"blend"}

    label = "Link Blend Hierarchy"
    icon = "code-fork"
    color = "orange"

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
        data = {
            "context": context,
            "name": name,
            "namespace": namespace,
            "group_name": group_name,
            "filepath": filepath,
            "options": options
        }
        loaded_collection = self.get_loaded_collection(**data)
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
        target_name = f"{container['namespace']}_{container['name']}"
        if collection.children:
            library = self._get_library_from_collection(collection.children[0])
            if library:
                bpy.data.libraries.remove(library)
            else:
                target_collection = find_collection_by_name(target_name)
                if target_collection:
                    for col in target_collection.children:
                        bpy.data.collections.remove(col)
                    for obj in target_collection.objects:
                        bpy.data.objects.remove(obj)

        # Remove the container collection
        bpy.data.collections.remove(collection)

        target_collection = find_collection_by_name(target_name)
        if target_collection:
            bpy.data.collections.remove(target_collection)

        target_object = find_objects_by_name(target_name)
        if target_object:
            bpy.data.objects.remove(target_object)

        return True

    def _get_library_from_collection(
            self, collection: bpy.types.Collection
    ) -> Optional[bpy.types.Library]:
        """Get the library from the collection."""
        for child in collection.children:
            if child.library:
                return child.library
            if child.override_library and child.override_library.reference:
                return child.override_library.reference.library

        for child in collection.objects:
            if child.library:
                return child.library
            if child.override_library and child.override_library.reference:
                return child.override_library.reference.library

        return None

    def get_loaded_collection(self, **kwargs)-> bpy.types.Collection:
        """Get the loaded collection.

        Returns:
            bpy.types.Collection: The loaded collection.
        """

        container_name = get_container_name(
            kwargs.get("name"),
            kwargs.get("namespace"),
            kwargs.get("context"),
            suffix="CON"
        )
        loaded_collection = bpy.data.collections.get(container_name)
        scene_collection = bpy.context.scene.collection
        group_name = kwargs.get("group_name")
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
            return loaded_collection

        return load_collection(
            kwargs.get("filepath"),
            link=True,
            group_name=group_name
        )


class BlendLinkLoaderFlat(BlendLinkLoader):
    """Link assets from a .blend file as flat Object."""

    product_types = {"blendScene"}
    label = "Link Blend (Flat)"

    instance_collections = False
    instance_object_data = False

    options = [
        BoolDef(
            "addOverride",
            label="Add Override",
            default=False,
            tooltip="Add a library override for the loaded asset.",
        ),
        BoolDef(
            "instance_collections",
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

    def get_loaded_collection(self, **kwargs) -> bpy.types.Collection:
        filepath = kwargs.get("filepath")
        group_name = kwargs.get("group_name")
        instance_collections = kwargs.get("options", {}).get(
            "instance_collections",
            self.instance_collections
        )
        instance_object_data = kwargs.get("options", {}).get(
            "instance_object_data", self.instance_object_data
        )
        return link_collection(
            filepath=filepath,
            group_name=group_name,
            instance_collections=instance_collections,
            instance_object_data=instance_object_data
        )
