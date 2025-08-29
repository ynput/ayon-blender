from __future__ import annotations
from typing import Optional
from pathlib import Path

import bpy

from ayon_core.pipeline import (
    AYON_CONTAINER_ID,
    registered_host
)
from ayon_core.pipeline.create import CreateContext
from ayon_blender.api import plugin
from ayon_blender.api.lib import imprint
from ayon_blender.api.pipeline import (
    add_to_ayon_container,
    get_ayon_property
)
from ayon_blender.api.constants import AYON_PROPERTY



class BlendLoader(plugin.BlenderLoader):
    """Load assets from a .blend file."""

    product_types = {"model", "rig", "layout", "camera"}
    representations = {"blend"}

    label = "Append Blend"
    icon = "code-fork"
    color = "orange"

    @staticmethod
    def _get_asset_container(objects):
        empties = [obj for obj in objects if obj.type == 'EMPTY']

        for empty in empties:
            # datablock is not allowed to
            empty_ayon_property = get_ayon_property(empty)
            if empty_ayon_property and empty.parent is None:
                return empty

        return None

    @staticmethod
    def get_all_container_parents(asset_group):
        parent_containers = []
        parent = asset_group.parent
        while parent:
            if parent.get(AYON_PROPERTY):
                parent_containers.append(parent)
            parent = parent.parent

        return parent_containers

    def _post_process_layout(self, container, asset, representation):
        rigs = [
            obj for obj in container.children_recursive
            if (
                obj.type == 'EMPTY' and
                obj.get(AYON_PROPERTY) and
                obj.get(AYON_PROPERTY).get('family') == 'rig'
            )
        ]
        if not rigs:
            return

        # Create animation instances for each rig
        creator_identifier = "io.ayon.creators.blender.animation"
        host = registered_host()
        create_context = CreateContext(host)

        for rig in rigs:
            create_context.create(
                creator_identifier=creator_identifier,
                variant=rig.name.split(':')[-1],
                pre_create_data={
                    "use_selection": False,
                    "asset_group": rig
                }
            )

    def _process_data(self, libpath, group_name):
        # Append all the data from the .blend file
        names_by_attr: dict[str, list[str]] = {}
        with bpy.data.libraries.load(
            libpath, link=False, relative=False
        ) as (data_from, data_to):
            for attr in dir(data_to):
                values = getattr(data_from, attr)
                # store copy of list of names because the main list will
                # be replaced with the data from the library after the context
                names_by_attr[attr] = list(values)
                setattr(data_to, attr, values)

        # Rename the object to add the asset name
        members = []
        for attr in dir(data_to):
            from_names: list[str] = names_by_attr[attr]
            for from_name, data in zip(from_names, getattr(data_to, attr)):
                data.name = f"{group_name}:{from_name}"
                members.append(data)

        container = self._get_asset_container(data_to.objects)
        assert container, "No asset group found"

        container.name = group_name
        container.empty_display_type = 'SINGLE_ARROW'

        # Link the collection to the scene
        bpy.context.scene.collection.objects.link(container)

        # Link all the container children to the collection
        for obj in container.children_recursive:
            bpy.context.scene.collection.objects.link(obj)

        # Remove the library from the blend file
        filepath = bpy.path.basename(libpath)
        # Blender has a limit of 63 characters for any data name.
        # If the filepath is longer, it will be truncated.
        if len(filepath) > 63:
            filepath = filepath[:63]
        library = bpy.data.libraries.get(filepath)
        bpy.data.libraries.remove(library)

        return container, members

    def process_asset(
        self, context: dict, name: str, namespace: Optional[str] = None,
        options: Optional[dict] = None
    ) -> Optional[list]:
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

        try:
            product_type = context["product"]["productType"]
        except ValueError:
            product_type = "model"

        representation = context["representation"]["id"]

        asset_name = plugin.prepare_scene_name(folder_name, product_name)
        unique_number = plugin.get_unique_number(folder_name, product_name)
        group_name = plugin.prepare_scene_name(
            folder_name, product_name, unique_number
        )
        namespace = namespace or f"{folder_name}_{unique_number}"

        container, members = self._process_data(libpath, group_name)

        if product_type == "layout":
            self._post_process_layout(container, folder_name, representation)

        add_to_ayon_container(container)

        data = {
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
            "members": members,
            "project_name": context["project"]["name"],
        }

        container[AYON_PROPERTY] = data

        objects = [
            obj for obj in bpy.data.objects
            if obj.name.startswith(f"{group_name}:")
        ]

        self[:] = objects
        return objects

    def exec_update(self, container: dict, context: dict):
        """
        Update the loaded asset.
        """
        repre_entity = context["representation"]
        group_name = container["objectName"]
        asset_group = bpy.data.objects.get(group_name)
        libpath = Path(self.filepath_from_context(context)).as_posix()

        assert asset_group, (
            f"The asset is not loaded: {container['objectName']}"
        )

        transform = asset_group.matrix_basis.copy()
        old_data = dict(asset_group.get(AYON_PROPERTY))
        old_members = old_data.get("members", [])
        parent = asset_group.parent
        users_collection = [
            collection for collection in asset_group.users_collection
        ]

        actions = {}
        objects_with_anim = [
            obj for obj in asset_group.children_recursive
            if obj.animation_data]
        for obj in objects_with_anim:
            # Check if the object has an action and, if so, add it to a dict
            # so we can restore it later. Save and restore the action only
            # if it wasn't originally loaded from the current asset.
            if obj.animation_data.action not in old_members:
                actions[obj.name] = obj.animation_data.action

        self.exec_remove(container)

        asset_group, members = self._process_data(libpath, group_name)

        add_to_ayon_container(asset_group)

        asset_group.matrix_basis = transform
        asset_group.parent = parent

        # Restore the actions
        for obj in asset_group.children_recursive:
            if obj.name in actions:
                if not obj.animation_data:
                    obj.animation_data_create()
                obj.animation_data.action = actions[obj.name]

        # Restore the old data, but reset members, as they don't exist anymore
        # This avoids a crash, because the memory addresses of those members
        # are not valid anymore
        old_data["members"] = []
        asset_group[AYON_PROPERTY] = old_data

        new_data = {
            "libpath": libpath,
            "representation": repre_entity["id"],
            "parent": repre_entity["versionId"],
            "members": members,
            "project_name": context["project"]["name"],
        }

        imprint(asset_group, new_data)

        if users_collection is not None:
            if asset_group.name not in users_collection.objects:
                all_objects = [asset_group] + list(asset_group.children_recursive)
                for obj in all_objects:
                    users_collection.objects.link(obj)

        # We need to update all the parent container members
        parent_containers = self.get_all_container_parents(asset_group)

        for parent_container in parent_containers:
            parent_members = parent_container[AYON_PROPERTY]["members"]
            parent_container[AYON_PROPERTY]["members"] = (
                parent_members + members)

    def exec_remove(self, container: dict) -> bool:
        """
        Remove an existing container from a Blender scene.
        """
        group_name = container["objectName"]
        asset_group = bpy.data.objects.get(group_name)

        attrs = [
            attr for attr in dir(bpy.data)
            if isinstance(
                getattr(bpy.data, attr),
                bpy.types.bpy_prop_collection
            )
        ]

        members = asset_group.get(AYON_PROPERTY).get("members", [])

        # We need to update all the parent container members
        parent_containers = self.get_all_container_parents(asset_group)

        for parent in parent_containers:
            parent.get(AYON_PROPERTY)["members"] = list(filter(
                lambda i: i not in members,
                parent.get(AYON_PROPERTY).get("members", [])))

        for attr in attrs:
            for data in getattr(bpy.data, attr):
                if data in members:
                    # Skip the asset group
                    if data == asset_group:
                        continue
                    getattr(bpy.data, attr).remove(data)

        bpy.data.objects.remove(asset_group)
