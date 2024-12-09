"""Load an action in Blender."""

import logging
from pathlib import Path
from pprint import pformat
from typing import Dict, List, Optional

import bpy
from ayon_core.pipeline import get_representation_path
from ayon_blender.api import plugin
from ayon_blender.api.pipeline import (
    containerise_existing,
    AVALON_PROPERTY,
)

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
        container_name = plugin.prepare_scene_name(
            folder_name, product_name, namespace
        )

        container = bpy.data.collections.new(lib_container)
        container.name = container_name
        containerise_existing(
            container,
            name,
            namespace,
            context,
            self.__class__.__name__,
        )

        container_metadata = container.get(AVALON_PROPERTY)

        container_metadata["libpath"] = libpath
        container_metadata["lib_container"] = lib_container

        relative = bpy.context.preferences.filepaths.use_relative_paths
        with bpy.data.libraries.load(
            libpath, link=True, relative=relative
        ) as (_, data_to):
            data_to.collections = [lib_container]

        collection = bpy.context.scene.collection

        collection.children.link(bpy.data.collections[lib_container])

        animation_container = collection.children[lib_container].make_local()

        objects_list = []

        # Link meshes first, then armatures.
        # The armature is unparented for all the non-local meshes,
        # when it is made local.
        for obj in animation_container.objects:

            obj = obj.make_local()

            anim_data = obj.animation_data

            if anim_data is not None and anim_data.action is not None:

                anim_data.action.make_local()

            if not obj.get(AVALON_PROPERTY):

                obj[AVALON_PROPERTY] = dict()

            avalon_info = obj[AVALON_PROPERTY]
            avalon_info.update({"container_name": container_name})

            objects_list.append(obj)

        animation_container.pop(AVALON_PROPERTY)

        # Save the list of objects in the metadata container
        container_metadata["objects"] = objects_list

        bpy.ops.object.select_all(action='DESELECT')

        nodes = list(container.objects)
        nodes.append(container)
        self[:] = nodes
        return nodes

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
        collection = bpy.data.collections.get(
            container["objectName"]
        )

        libpath = Path(get_representation_path(repre_entity))
        extension = libpath.suffix.lower()

        logger.info(
            "Container: %s\nRepresentation: %s",
            pformat(container, indent=2),
            pformat(repre_entity, indent=2),
        )

        assert collection, (
            f"The asset is not loaded: {container['objectName']}"
        )
        assert not (collection.children), (
            "Nested collections are not supported."
        )
        assert libpath, (
            "No existing library file found for {container['objectName']}"
        )
        assert libpath.is_file(), (
            f"The file doesn't exist: {libpath}"
        )
        assert extension in plugin.VALID_EXTENSIONS, (
            f"Unsupported file: {libpath}"
        )

        collection_metadata = collection.get(AVALON_PROPERTY)

        collection_libpath = collection_metadata["libpath"]
        normalized_collection_libpath = (
            str(Path(bpy.path.abspath(collection_libpath)).resolve())
        )
        normalized_libpath = (
            str(Path(bpy.path.abspath(str(libpath))).resolve())
        )
        logger.debug(
            "normalized_collection_libpath:\n  %s\nnormalized_libpath:\n  %s",
            normalized_collection_libpath,
            normalized_libpath,
        )
        if normalized_collection_libpath == normalized_libpath:
            logger.info("Library already loaded, not updating...")
            return

        strips = []

        for obj in list(collection_metadata["objects"]):
            # Get all the strips that use the action
            arm_objs = [
                arm for arm in bpy.data.objects if arm.type == 'ARMATURE']

            for armature_obj in arm_objs:
                if armature_obj.animation_data is not None:
                    for track in armature_obj.animation_data.nla_tracks:
                        for strip in track.strips:
                            if strip.action == obj.animation_data.action:
                                strips.append(strip)

            bpy.data.actions.remove(obj.animation_data.action)
            bpy.data.objects.remove(obj)

        lib_container = collection_metadata["lib_container"]

        bpy.data.collections.remove(bpy.data.collections[lib_container])

        relative = bpy.context.preferences.filepaths.use_relative_paths
        with bpy.data.libraries.load(
            str(libpath), link=True, relative=relative
        ) as (_, data_to):
            data_to.collections = [lib_container]

        scene = bpy.context.scene

        scene.collection.children.link(bpy.data.collections[lib_container])

        anim_container = scene.collection.children[lib_container].make_local()

        objects_list = []

        # Link meshes first, then armatures.
        # The armature is unparented for all the non-local meshes,
        # when it is made local.
        for obj in anim_container.objects:

            obj = obj.make_local()

            anim_data = obj.animation_data

            if anim_data is not None and anim_data.action is not None:

                anim_data.action.make_local()

                for strip in strips:

                    strip.action = anim_data.action
                    strip.action_frame_end = anim_data.action.frame_range[1]

            if not obj.get(AVALON_PROPERTY):

                obj[AVALON_PROPERTY] = dict()

            avalon_info = obj[AVALON_PROPERTY]
            avalon_info.update({"container_name": collection.name})

            objects_list.append(obj)

        anim_container.pop(AVALON_PROPERTY)

        # Save the list of objects in the metadata container
        collection_metadata["objects"] = objects_list
        collection_metadata["libpath"] = str(libpath)
        collection_metadata["representation"] = repre_entity["id"]
        collection_metadata["project_name"] = context["project"]["name"]

        bpy.ops.object.select_all(action='DESELECT')

    def remove(self, container: Dict) -> bool:
        """Remove an existing container from a Blender scene.

        Arguments:
            container (openpype:container-1.0): Container to remove,
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
        assert not (collection.children), (
            "Nested collections are not supported."
        )

        collection_metadata = collection.get(AVALON_PROPERTY)
        objects = collection_metadata["objects"]
        lib_container = collection_metadata["lib_container"]

        for obj in list(objects):
            # Get all the strips that use the action
            arm_objs = [
                arm for arm in bpy.data.objects if arm.type == 'ARMATURE']

            for armature_obj in arm_objs:
                if armature_obj.animation_data is not None:
                    for track in armature_obj.animation_data.nla_tracks:
                        for strip in track.strips:
                            if strip.action == obj.animation_data.action:
                                track.strips.remove(strip)

            bpy.data.actions.remove(obj.animation_data.action)
            bpy.data.objects.remove(obj)

        bpy.data.collections.remove(bpy.data.collections[lib_container])
        bpy.data.collections.remove(collection)

        return True
