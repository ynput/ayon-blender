"""Load a look (materials) in Blender."""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import ayon_api

from ayon_core.lib import BoolDef, EnumDef
from ayon_core.pipeline.load import LoadError
from ayon_blender.api import lib, plugin
from ayon_blender.api.pipeline import (
    containerise_existing,
    metadata_update,
    ls,
)
from ayon_blender.api.constants import AYON_PROPERTY

import bpy


class BlendLookLoader(plugin.BlenderLoader):
    """Load material datablock from a .blend file.

    When the look has a 'json' representation with the material assignments
    (published alongside the .blend file), the materials are assigned to the
    objects with matching names. On update, the assignments are re-applied
    to the objects that use the look's materials.
    """

    product_base_types = {"look"}
    product_types = product_base_types
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
        ),
        EnumDef(
            "assign_materials",
            label="Assign Materials",
            items=[
                {"value": "selected",
                 "label": "Selected objects (and children)"},
                {"value": "scene", "label": "All objects in scene"},
                {"value": "none", "label": "Don't assign"},
            ],
            default="selected",
            tooltip=(
                "Assign the look materials to objects whose names match"
                " the objects the look was published with."
            ),
        ),
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

    @staticmethod
    def _link_materials(libpath: str) -> List[bpy.types.Material]:
        """Link all materials (and images) from the library file."""
        relative = bpy.context.preferences.filepaths.use_relative_paths
        with bpy.data.libraries.load(
            libpath, link=True, relative=relative
        ) as (data_from, data_to):
            data_to.materials = data_from.materials
            data_to.images = data_from.images
        return [
            material for material in data_to.materials
            if material is not None
        ]

    def _get_material_assignments(self, context: dict) -> Optional[dict]:
        """Get the material assignments published with the look version.

        Returns:
            Optional[dict]: The material assignments ('relationships') or
                None when the version has no 'json' representation, e.g.
                looks published before assignments were recorded.
        """
        project_name = context["project"]["name"]
        version_id = context["version"]["id"]
        repre_entity = next(
            iter(ayon_api.get_representations(
                project_name,
                representation_names={"json"},
                version_ids={version_id},
            )),
            None
        )
        if not repre_entity:
            self.log.info(
                "No material assignments ('json' representation) found for"
                " this look version. Skipping material assignment."
            )
            return None

        path = self.filepath_from_context(
            {**context, "representation": repre_entity}
        )
        if not os.path.exists(path):
            self.log.warning(
                "Material assignments file not found: %s", path
            )
            return None

        with open(path, "r") as f:
            return json.load(f).get("relationships", {})

    @staticmethod
    def _get_objects_to_assign(scope: str) -> List[bpy.types.Object]:
        """Return the objects to consider for material assignment."""
        if scope == "scene":
            return list(bpy.context.scene.objects)
        if scope == "selected":
            objects = []
            for obj in lib.get_selection():
                objects.append(obj)
                objects.extend(obj.children_recursive)
            return objects
        return []

    @staticmethod
    def _get_objects_using_library(
        library: Optional[bpy.types.Library]
    ) -> List[bpy.types.Object]:
        """Return objects with a material from the library assigned."""
        if not library:
            return []
        return [
            obj for obj in bpy.data.objects
            if any(
                slot.material and slot.material.library == library
                for slot in obj.material_slots
            )
        ]

    def _assign_materials(
        self,
        context: dict,
        materials: List[bpy.types.Material],
        objects: List[bpy.types.Object],
    ):
        """Assign materials to the objects by matching names."""
        if not objects:
            return
        try:
            relationships = self._get_material_assignments(context)
        except Exception:
            # Do not fail loading the materials when the assignments
            # cannot be retrieved
            self.log.error(
                "Failed to get the material assignments of the look.",
                exc_info=True
            )
            return
        if not relationships:
            return
        assigned = lib.assign_materials_by_name(
            relationships, materials, objects, logger=self.log
        )
        if assigned:
            self.log.info(
                "Assigned look materials to %d object(s).", len(assigned)
            )
        else:
            self.log.warning(
                "No objects with matching names found to assign the look"
                " materials to."
            )

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
        options = options or {}
        libpath = self.filepath_from_context(context)
        folder_name = context["folder"]["name"]
        product_name = context["product"]["name"]
        lib_container = plugin.prepare_scene_name(folder_name, product_name)

        # Get the objects to assign the materials to before the selection
        # is cleared
        assign_scope = options.get("assign_materials", "selected")
        objects_to_assign = self._get_objects_to_assign(assign_scope)
        if assign_scope == "selected" and not objects_to_assign:
            self.log.warning(
                "No objects selected to assign the look materials to."
            )

        container = bpy.data.collections.new(lib_container)
        containerise_existing(
            container,
            name,
            namespace,
            context,
            self.__class__.__name__,
        )

        container_metadata = container.get(AYON_PROPERTY)

        materials = self._link_materials(libpath)
        if not materials:
            raise LoadError(
                "No material found in the file, please check if "
                "there is any material datablock in the blend file."
            )
        for material in materials:
            material.use_fake_user = options.get("use_fake_user", True)
        container_metadata["library"] = next(
            material.library for material
            in materials if material.library
        )
        metadata_update(container, container_metadata)

        self._assign_materials(context, materials, objects_to_assign)

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

        # Objects using the current look materials get the material
        # assignments of the new version re-applied after the update
        objects_to_assign = self._get_objects_using_library(library)

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
                self._reassign_after_update(
                    context, libpath, objects_to_assign
                )
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

        self._reassign_after_update(context, libpath, objects_to_assign)

    def _reassign_after_update(
        self,
        context: Dict,
        libpath: str,
        objects: List[bpy.types.Object],
    ):
        """Re-apply the material assignments of the updated look version.

        Materials that are new in this version are linked as well, so they
        can be assigned.
        """
        if not objects:
            return
        materials = self._link_materials(libpath)
        for material in materials:
            # Protect newly linked, unassigned materials from being purged
            if not material.users:
                material.use_fake_user = True
        self._assign_materials(context, materials, objects)

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
