"""Load an action in Blender."""

import os
import logging
from typing import Dict, List, Optional

import bpy
from ayon_core.lib import BoolDef
from ayon_core.pipeline.load import LoadError

from ayon_blender.api import plugin
from ayon_blender.api.pipeline import (
    containerise_existing,
    metadata_update
)
from ayon_blender.api.constants import AYON_PROPERTY


logger = logging.getLogger("ayon").getChild("blender").getChild("load_action")


class BlendActionLoader(plugin.BlenderLoader):
    """Load action from a .blend file.

    Warning:
        Loading the same asset more then once is not properly supported at the
        moment.
    """

    product_types = {"action"}
    representations = {"blend"}

    label = "Link Action"
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
            data_to.actions = data_from.actions
        if not data_to.actions:
            raise LoadError(
                "No action found in the file, please check if "
                "there is any action datablock in the blend file."
            )
        container = data_to.actions[0]

        empty_obj = bpy.data.objects.new(name=name, object_data=None)
        empty_obj.animation_data_create()
        empty_obj.animation_data.action = container
        empty_obj.animation_data.action.use_fake_user = options.get(
            "use_fake_user", True
        )
        # Save the list of objects in the metadata container
        container_metadata["libpath"] = libpath
        container_metadata["lib_container"] = lib_container
        container_metadata["objects"] = empty_obj
        container_metadata["action"] = empty_obj.animation_data.action

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
        action = container["action"]
        if action.library:
            action.library.name = os.path.basename(libpath)
            action.library.filepath = libpath

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

        action = container["action"]
        bpy.data.actions.remove(action)
        bpy.data.collections.remove(collection)

        return True
