"""Load a model asset in Blender."""

from pathlib import Path
from pprint import pformat
from typing import Dict, List, Optional

import os
import json
import bpy

from ayon_core.lib import BoolDef
from ayon_core.pipeline.load import LoadError
from ayon_blender.api import plugin
from ayon_blender.api.pipeline import (
    containerise_existing,
    metadata_update
)
from ayon_blender.api.constants import AYON_PROPERTY


class BlendLookLoader(plugin.BlenderLoader):
    """Load material datablock from a .blend file."""

    product_types = {"look"}
    representations = {"blend"}

    label = "Load Look"
    icon = "code-fork"
    color = "orange"


    options = [
        BoolDef(
            "use_fake_user",
            label="Use Fake User",
            default=True,
            tooltip="Set the fake user for the loaded asset.",
        )
    ]

    def process_asset(
        self, context: dict, name: str, namespace: Optional[str] = None,
        options: Optional[Dict] = None
    ) -> Optional[List]:
        """
        Arguments:
            name: Use pre-defined name
            namespace: Use pre-defined namespace
            context: Full parenthood of representation to load
            options: Additional settings dictionary
        """

        libpath = self.filepath_from_context(context)
        folder_name = context["folder"]["name"]
        product_name = context["product"]["name"]
        lib_container = plugin.prepare_scene_name(folder_name, product_name)

        container = bpy.data.collections.new(lib_container)
        containerise_existing(
            container,
            name,
            namespace,
            context,
            self.__class__.__name__,
        )

        container_metadata = container.get(AYON_PROPERTY)


        relative = bpy.context.preferences.filepaths.use_relative_paths
        with bpy.data.libraries.load(
            libpath, link=True, relative=relative
        ) as (data_from, data_to):
            data_to.materials = data_from.materials
        if not data_to.materials:
            raise LoadError(
                "No material found in the file, please check if "
                "there is any material datablock in the blend file."
            )
        container = data_to.materials[0]

        empty_obj = bpy.data.objects.new(name=name, object_data=None)
        empty_obj.active_material = container
        empty_obj.active_material.use_nodes = True
        empty_obj.active_material.use_fake_user = options.get(
            "use_fake_user", True
        )
        # Save the list of objects in the metadata container
        container_metadata["libpath"] = libpath
        container_metadata["lib_container"] = lib_container
        container_metadata["objects"] = empty_obj
        container_metadata["material"] = empty_obj.active_material
        empty_obj.data.materials.append(empty_obj.active_material)

        metadata_update(container, container_metadata)
        bpy.ops.object.select_all(action='DESELECT')
        self[:] = [empty_obj]

        return container

    def update(self, container: Dict, context: Dict):
        """Update the loaded asset.

        This will remove all objects of the current collection, load the new
        ones and add them to the collection.
        If the objects of the collection are used in another collection they
        will not be removed, only unlinked. Normally this should not be the
        case though.

        Warning:
            No nested collections are supported at the moment!
        """
        repre_entity = context["representation"]
        collection = container["node"]
        libpath = self.filepath_from_context(context)
        material = container["material"]
        if material.library:
            material.library.name = os.path.basename(libpath)
            material.library.filepath = libpath

        metadata_update(
            collection, {"representation": str(repre_entity["id"])}
        )

    def remove(self, container: Dict) -> bool:
        """Remove an existing container from a Blender scene.

        Arguments:
            container (ayon:container-1.0): Container to remove,
                from `host.ls()`.

        Returns:
            bool: Whether the container was deleted.

        Warning:
            No nested collections are supported at the moment!
        """

        collection = bpy.data.collections.get(
            container["objectName"]
        )
        if not collection:
            return False

        material = container["material"]
        bpy.data.materials.remove(material)
        bpy.data.collections.remove(collection)

        return True
