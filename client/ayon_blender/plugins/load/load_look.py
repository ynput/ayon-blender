"""Load a model asset in Blender."""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ayon_core.lib import BoolDef
from ayon_core.pipeline.load import LoadError
from ayon_blender.api import plugin
from ayon_blender.api.pipeline import (
    containerise_existing,
    metadata_update,
    ls,
)
from ayon_blender.api.constants import AYON_PROPERTY

import bpy


class BlendLookLoader(plugin.BlenderLoader):
    """Load material datablock from a .blend file."""

    product_types = {"look"}
    representations = {"*"}
    extensions = {"blend"}

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

    def get_existing_library(self, libpath: str) -> Optional[bpy.types.Library]:
        """Get the existing library if it's already loaded."""
        for library in bpy.data.libraries:
            if library and Path(library.filepath) == Path(libpath):
                return library
        return None

    def _is_containerized(self, library: str) -> bool:
        """Check if there is an existing container for the given library path."""
        for container in ls():
            if container.get("loader") != self.__class__.__name__:
                # Only consider containers of this particular loader
                continue
            if container.get("library") != library:
                continue
            return True
        return False

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
            data_to.images = data_from.images

        if not data_to.materials:
            raise LoadError(
                "No material found in the file, please check if "
                "there is any material datablock in the blend file."
            )
        materials = data_to.materials
        for material in materials:
            material.use_fake_user = options.get("use_fake_user", True)
        container_metadata["library"] = next(
            material.library for material
            in materials if material.library
        )
        metadata_update(container, container_metadata)
        bpy.ops.object.select_all(action='DESELECT')
        self[:] = [materials]

        return container

    def update(self, container: Dict, context: Dict):
        """Update the loaded material datalock.

        Args:
            container (Dict): The container to update.
            context (Dict): The context of the update.
        """
        repre_entity = context["representation"]
        collection = container["node"]
        library = container["library"]
        libpath = self.filepath_from_context(context)
        existing_library = self.get_existing_library(libpath)

        # The new path may be the same path the library is already set to when
        # updating to same version (which would merely force a reload) but
        # we'll need to account for that case.
        is_same_library = existing_library == library

        # Even if there is an existing library with the same path we want to
        # set the path on this library to match the existing one. Then Blender
        # will end up 'merging' the libraries together, remapping all usage.
        library.name = os.path.basename(libpath)
        library.filepath = libpath
        library.reload()

        new_metadata: dict[str, Any] = {}
        if existing_library and not is_same_library:
            if self._is_containerized(existing_library):
                # This library has now merged into the existing library
                # and with that all its users have been remapped.
                # Essentially containers would have merged.
                self.log.info(
                    "Library already exists."
                    " Merging container with existing containerized library."
                )
                self.remove(container)
                return
            else:
                # Update current container to point to the
                # existing library
                self.log.info(
                    "Library already exists."
                    " Updating container library to use existing library."
                )
                new_metadata["library"] = existing_library

        new_metadata["representation"] = repre_entity["id"]
        metadata_update(collection, new_metadata)

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

        library = container["library"]
        # if library users is more than 1, it means
        # that there are other materials or images
        if library and library.users <= 1:
            bpy.data.libraries.remove(library)

        bpy.data.collections.remove(collection)

        return True
