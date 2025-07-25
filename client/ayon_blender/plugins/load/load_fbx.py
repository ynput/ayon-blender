"""Load an asset in Blender from an Alembic file."""

from pathlib import Path
from pprint import pformat
from typing import Dict, List, Optional

import bpy

from ayon_core.pipeline import AYON_CONTAINER_ID
from ayon_blender.api import plugin, lib
from ayon_blender.api.constants import (
    AYON_PROPERTY,
    VALID_EXTENSIONS,
)
from ayon_blender.api.pipeline import add_to_ayon_container


class FbxModelLoader(plugin.BlenderLoader):
    """Load FBX models.

    Stores the imported asset in an empty named after the asset.
    """

    product_types = {"model", "rig"}
    representations = {"fbx"}

    label = "Load FBX"
    icon = "code-fork"
    color = "orange"

    def _remove(self, asset_group):
        objects = list(asset_group.children)

        for obj in objects:
            if obj.type == 'MESH':
                for material_slot in list(obj.material_slots):
                    if material_slot.material:
                        bpy.data.materials.remove(material_slot.material)
                bpy.data.meshes.remove(obj.data)
            elif obj.type == 'ARMATURE':
                objects.extend(obj.children)
                bpy.data.armatures.remove(obj.data)
            elif obj.type == 'CURVE':
                bpy.data.curves.remove(obj.data)
            elif obj.type == 'EMPTY':
                objects.extend(obj.children)
                bpy.data.objects.remove(obj)

    def _process(self, libpath, asset_group, group_name, action):
        plugin.deselect_all()

        blender_version = lib.get_blender_version()
        # bpy.ops.wm.fbx_import would be the new python command for
        # fbx loader and it would fully replace its old version of
        # bpy.ops.import_scene.fbx to be the default import command
        # in 5.0
        if blender_version >= (4, 5, 0):
            bpy.ops.wm.fbx_import(filepath=libpath)
        else:
            # TODO: make sure it works with the color management
            # in 4.4 or elder version
            bpy.ops.import_scene.fbx(filepath=libpath)

        parent = bpy.context.scene.collection

        imported = lib.get_selection()

        empties = [obj for obj in imported if obj.type == 'EMPTY']

        container = None

        for empty in empties:
            if not empty.parent:
                container = empty
                break

        assert container, "No asset group found"

        # Children must be linked before parents,
        # otherwise the hierarchy will break
        objects = []
        nodes = list(container.children)

        for obj in nodes:
            obj.parent = asset_group

        bpy.data.objects.remove(container)

        for obj in nodes:
            objects.append(obj)
            nodes.extend(list(obj.children))

        objects.reverse()

        for obj in objects:
            if obj.name not in parent.objects:
                parent.objects.link(obj)

        for obj in objects:
            name = obj.name
            obj.name = f"{group_name}:{name}"
            if obj.type != 'EMPTY':
                name_data = obj.data.name
                obj.data.name = f"{group_name}:{name_data}"

            if obj.type == 'MESH':
                for material_slot in obj.material_slots:
                    name_mat = material_slot.material.name
                    material_slot.material.name = f"{group_name}:{name_mat}"
            elif obj.type == 'ARMATURE':
                anim_data = obj.animation_data
                if action is not None:
                    anim_data.action = action
                elif anim_data and anim_data.action:
                    name_action = anim_data.action.name
                    anim_data.action.name = f"{group_name}:{name_action}"

            if not obj.get(AYON_PROPERTY):
                obj[AYON_PROPERTY] = dict()

            ayon_info = obj[AYON_PROPERTY]
            ayon_info.update({"container_name": group_name})

        plugin.deselect_all()

        return objects

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
        add_to_ayon_container(asset_group)

        objects = self._process(libpath, asset_group, group_name, None)

        objects = []
        nodes = list(asset_group.children)

        for obj in nodes:
            objects.append(obj)
            nodes.extend(list(obj.children))

        bpy.context.scene.collection.objects.link(asset_group)

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
            "productType": context["product"]["productType"],
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

        # Get the armature of the rig
        objects = asset_group.children
        armatures = [obj for obj in objects if obj.type == 'ARMATURE']
        action = None

        if armatures:
            armature = armatures[0]

            if armature.animation_data and armature.animation_data.action:
                action = armature.animation_data.action

        mat = asset_group.matrix_basis.copy()
        self._remove(asset_group)

        self._process(str(libpath), asset_group, object_name, action)

        asset_group.matrix_basis = mat

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
