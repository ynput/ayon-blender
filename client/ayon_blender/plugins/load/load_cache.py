"""Load an asset in Blender from an Alembic file."""

from pathlib import Path
from pprint import pformat
from typing import Dict, List, Optional

import bpy
import os

from ayon_core.pipeline import AYON_CONTAINER_ID

from ayon_blender.api.constants import (
    AYON_PROPERTY,
    VALID_EXTENSIONS,
)
from ayon_blender.api import plugin, lib
from ayon_blender.api.pipeline import (
    add_to_ayon_container,
    get_ayon_container
)


class CacheModelLoader(plugin.BlenderLoader):
    """Load cache models.

    Stores the imported asset in a collection named after the asset.

    Note:
        At least for now it only supports Alembic files.
    """
    product_types = {"model", "pointcache", "animation", "usd"}
    representations = {"abc", "usd"}

    label = "Load Cache"
    icon = "code-fork"
    color = "orange"

    def _update_transform_cache_path(self, asset_group, libpath, prev_filename):
        """search and update path in the transform cache modifier
        If there is no transform cache modifier, it will create one
        to update the filepath of the alembic.
        """
        bpy.ops.cachefile.open(filepath=libpath.as_posix())
        for obj in asset_group.children:
            asset_name = obj.name.rsplit(":", 1)[-1]
            names = [modifier.name for modifier in obj.modifiers
                     if modifier.type == "MESH_SEQUENCE_CACHE"]
            file_list = [file for file in bpy.data.cache_files
                         if file.name.startswith(prev_filename)]
            if names:
                for name in names:
                    obj.modifiers.remove(obj.modifiers.get(name))
            if file_list:
                bpy.data.batch_remove(file_list)

            obj.modifiers.new(name='MeshSequenceCache', type='MESH_SEQUENCE_CACHE')

            modifiers = lib.get_cache_modifiers(obj)
            for asset_name, modifier_list in modifiers.items():
                for modifier in modifier_list:
                    if modifier.type == "MESH_SEQUENCE_CACHE":
                        modifier.cache_file = bpy.data.cache_files[-1]
                        cache_file_name = os.path.basename(libpath.as_posix())
                        modifier.cache_file.name = cache_file_name
                        modifier.cache_file.filepath = libpath.as_posix()
                        modifier.cache_file.scale = 1.0
                        for object_path in modifier.cache_file.object_paths:
                            base_object_name = os.path.basename(object_path.path)
                            asset_name = asset_name.rsplit(":", 1)[-1]
                            if base_object_name.endswith(asset_name):
                                modifier.object_path = object_path.path
                        bpy.context.evaluated_depsgraph_get()

        return libpath

    def _remove(self, asset_group):
        objects = list(asset_group.children)
        empties = []

        for obj in objects:
            if obj.type == 'MESH':
                for material_slot in list(obj.material_slots):
                    bpy.data.materials.remove(material_slot.material)
                bpy.data.meshes.remove(obj.data)
            elif obj.type == 'EMPTY':
                objects.extend(obj.children)
                empties.append(obj)

        for empty in empties:
            bpy.data.objects.remove(empty)

    def _process(self, libpath, asset_group, group_name):
        plugin.deselect_all()

        relative = bpy.context.preferences.filepaths.use_relative_paths

        if any(libpath.lower().endswith(ext)
               for ext in [".usd", ".usda", ".usdc"]):
            # USD
            bpy.ops.wm.usd_import(
                filepath=libpath,
                relative_path=relative
            )

        else:
            # Alembic
            bpy.ops.wm.alembic_import(
                filepath=libpath,
                relative_path=relative
            )

        objects = lib.get_selection()

        for obj in objects:
            # reparent top object to asset_group
            if not obj.parent:
                obj.parent = asset_group

            # Unlink the object from all collections
            collections = obj.users_collection
            for collection in collections:
                collection.objects.unlink(obj)
            name = obj.name
            obj.name = f"{group_name}:{name}"
            if obj.type != 'EMPTY':
                name_data = obj.data.name
                obj.data.name = f"{group_name}:{name_data}"

                for material_slot in obj.material_slots:
                    name_mat = material_slot.material.name
                    material_slot.material.name = f"{group_name}:{name_mat}"

            if not obj.get(AYON_PROPERTY):
                obj[AYON_PROPERTY] = {}

            ayon_info = obj[AYON_PROPERTY]
            ayon_info.update({"container_name": group_name})

        plugin.deselect_all()

        return objects

    def _link_objects(self, objects, collection, container):
        # Link the imported objects to any collection where the asset group is
        # linked to, except the AYON_CONTAINERS collection
        group_collections = [
            collection
            for collection in collection.users_collection
            if collection != container]

        for obj in objects:
            for collection in group_collections:
                collection.objects.link(obj)

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

        asset_name = plugin.prepare_scene_name(folder_name, product_name)
        unique_number = plugin.get_unique_number(folder_name, product_name)
        group_name = plugin.prepare_scene_name(
            folder_name, product_name, unique_number
        )
        namespace = namespace or f"{folder_name}_{unique_number}"

        asset_group = bpy.data.objects.new(group_name, object_data=None)
        asset_group.empty_display_type = 'SINGLE_ARROW'
        add_to_ayon_container(asset_group)
        objects = self._process(libpath, asset_group, group_name)

        # Link the asset group to the active collection
        collection = bpy.context.view_layer.active_layer_collection.collection
        collection.objects.link(asset_group)
        container = get_ayon_container()
        self._link_objects(objects, asset_group, container)

        product_type = context["product"]["productType"]
        asset_group[AYON_PROPERTY] = {
            "schema": "ayon:container-3.0",
            "id": AYON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
            "libpath": libpath,
            "asset_name": asset_name,
            "parent": context["representation"]["versionId"],
            "productType": product_type,
            "objectName": group_name,
            "project_name": context["project"]["name"],
        }

        self[:] = objects
        return objects

    def exec_update(self, container: Dict, context: Dict):
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
        object_name = container["objectName"]
        asset_group = bpy.data.objects.get(object_name)
        libpath = Path(self.filepath_from_context(context))
        extension = libpath.suffix.lower()

        self.log.info(
            "Container: %s\nRepresentation: %s",
            pformat(container, indent=2),
            pformat(repre_entity, indent=2),
        )

        assert asset_group, (
            f"The asset is not loaded: {container['objectName']}"
        )
        assert libpath, (
            "No existing library file found for {container['objectName']}"
        )
        assert libpath.is_file(), (
            f"The file doesn't exist: {libpath}"
        )
        assert extension in VALID_EXTENSIONS, (
            f"Unsupported file: {libpath}"
        )

        metadata = asset_group.get(AYON_PROPERTY)
        group_libpath = metadata["libpath"]

        normalized_group_libpath = (
            str(Path(bpy.path.abspath(group_libpath)).resolve())
        )
        normalized_libpath = (
            str(Path(bpy.path.abspath(str(libpath))).resolve())
        )
        self.log.debug(
            "normalized_group_libpath:\n  %s\nnormalized_libpath:\n  %s",
            normalized_group_libpath,
            normalized_libpath,
        )
        if normalized_group_libpath == normalized_libpath:
            self.log.info("Library already loaded, not updating...")
            return

        if any(str(libpath).lower().endswith(ext)
               for ext in [".usd", ".usda", ".usdc"]):
            mat = asset_group.matrix_basis.copy()
            self._remove(asset_group)

            objects = self._process(str(libpath), asset_group, object_name)

            container = get_ayon_container()
            self._link_objects(objects, asset_group, container)

            asset_group.matrix_basis = mat
        else:
            prev_filename = os.path.basename(container["libpath"])
            libpath = self._update_transform_cache_path(asset_group, libpath, prev_filename)


        metadata["libpath"] = str(libpath)
        metadata["representation"] = repre_entity["id"]
        metadata["project_name"] = context["project"]["name"]

    def exec_remove(self, container: Dict) -> bool:
        """Remove an existing container from a Blender scene.

        Arguments:
            container (ayon:container-1.0): Container to remove,
                from `host.ls()`.

        Returns:
            bool: Whether the container was deleted.

        Warning:
            No nested collections are supported at the moment!
        """
        object_name = container["objectName"]
        asset_group = bpy.data.objects.get(object_name)

        if not asset_group:
            return False

        self._remove(asset_group)

        bpy.data.objects.remove(asset_group)

        return True
