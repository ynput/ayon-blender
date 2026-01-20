import logging
from typing import Generator, TYPE_CHECKING

import bpy
from ayon_core.pipeline.load import LoadError
from ayon_blender.api.pipeline import AVALON_PROPERTY

if TYPE_CHECKING:
    from ayon_core.pipeline.create import CreateContext  # noqa: F401


log = logging.getLogger(__name__)


def add_override(
    loaded_collection: bpy.types.Collection,
) -> bpy.types.Collection:
    """Add overrides for the loaded armatures."""
    overridden_collections = list(
        get_overridden_collections_from_reference_collection(loaded_collection)
    )
    context = bpy.context
    scene = context.scene
    loaded_objects = loaded_collection.all_objects
    # This slightly convoluted way of running the operator seems necessary to
    # have it work reliably for more than 1 rig on both Linux and Windows.
    # Giving it a 'random' object from the collection seems to override
    # everything contained in the loaded collection.
    context.view_layer.objects.active = loaded_objects[0]

    from .plugin import create_blender_context  # todo: move import
    operator_context = create_blender_context(
        active=loaded_objects[0],
        selected=loaded_objects
    )

    # https://blender.stackexchange.com/questions/289245/how-to-make-a-blender-library-override-in-python  # noqa
    # https://docs.blender.org/api/current/bpy.types.ID.html#bpy.types.ID.override_hierarchy_create  # noqa
    if bpy.app.version[0] >= 4:
        with bpy.context.temp_override(**operator_context):
            loaded_collection.override_hierarchy_create(
                scene, context.view_layer, do_fully_editable=True
            )

    scene.collection.children.unlink(loaded_collection)

    if overridden_collections:
        local_collection = get_local_collection(
            overridden_collections,
            loaded_collection,
        )
    else:
        local_collection = loaded_collection

    return local_collection


def get_local_collection(
    overridden_collections: list[bpy.types.Collection],
    loaded_collection: bpy.types.Collection,
) -> bpy.types.Collection:
    """Get the local (overridden) collection.

    To get it we check all collections with a library override and check if
    they have the loaded collection as their reference. If a collection is
    not in the provided (known) override collections, we assume it's the newly
    created one.
    """
    local_collections: set[bpy.types.Collection] = set()
    for collection in get_overridden_collections_from_reference_collection(
        loaded_collection
    ):
        if collection not in overridden_collections:
            local_collections.add(collection)
    if len(local_collections) != 1:
        raise RuntimeError("Could not find the overridden collection.")

    return local_collections.pop()


def get_overridden_collections_from_reference_collection(
    reference_collection: bpy.types.Collection,
) -> Generator[bpy.types.Collection, None, None]:
    """Get collections that are overridden versions of the reference collection.

    Yields:
        All collections that have an override library and have the
        `reference_collection` collection as reference.
    """
    for collection in bpy.data.collections:
        if not collection.override_library:
            continue
        if collection.override_library.reference == reference_collection:
            yield collection


def get_asset_container(objects):
    empties = [obj for obj in objects if obj.type == 'EMPTY']

    for empty in empties:
        if empty.get(AVALON_PROPERTY) and empty.parent is None:
            return empty

    return None


import os
import re
import bpy

def load_collection(
    filepath,
    link=True,
    lib_container_name=None,
    group_name=None
) -> bpy.types.Collection:
    """Load a collection to the scene using bpy.ops.wm.link (UI 1:1 behavior)."""

    asset_container = get_collection(group_name)

    # ------------------------------------------------------------------
    # 1) Discover collections available in the library (cheap, no linking)
    # ------------------------------------------------------------------
    with bpy.data.libraries.load(filepath, link=False, relative=False) as (data_from, data_to):
        lib_collections = list(data_from.collections)

    # ------------------------------------------------------------------
    # 2) Choose what to link
    #    group_name is the collection we are looking for in the published file.
    #    We will link exactly that collection by name.
    # ------------------------------------------------------------------
    # Normalize group_name to desired published collection name:
    # Example:
    #   group_name:            general_01_assembly_ManWoman
    #   desired collection:    general_assembly_ManWoman
    # Rule: remove the second token if it is exactly two digits (e.g. "_01_").
    target_name = re.sub(r"^([^_]+)_\d{2}_(.+)$", r"\1_\2", group_name)

    if target_name not in lib_collections:
        raise LoadError(
            f"load_collection: target collection '{target_name}' not found in library."
        )

    # ------------------------------------------------------------------
    # 3) Link using the operator with UI toggles OFF
    # ------------------------------------------------------------------
    directory = os.path.join(filepath, "Collection") + os.sep
    op_filepath = directory + target_name

    # Ensure Blender links into our AYON container collection to avoid creating "LinkedData"
    try:
        view_layer = bpy.context.view_layer

        def _find_layer_collection(layer_coll, collection):
            if layer_coll.collection == collection:
                return layer_coll
            for ch in layer_coll.children:
                found = _find_layer_collection(ch, collection)
                if found:
                    return found
            return None

        lc = _find_layer_collection(view_layer.layer_collection, asset_container)
        if lc:
            view_layer.active_layer_collection = lc
    except Exception:
        pass

    bpy.ops.wm.link(
        filepath=op_filepath,
        directory=directory,
        filename=target_name,
        # link=True means keep data linked (AYON link workflow)
        link=link,
        relative_path=False,

        # Make behavior match UI toggles 1:1
        instance_collections=False,
        instance_object_data=False,

        # Keep selection side effects minimal
        autoselect=False,
        active_collection=True,
    )

    # ------------------------------------------------------------------
    # 4) Retrieve the linked collection datablock and ensure it's parented under asset_container
    # ------------------------------------------------------------------
    linked_coll = bpy.data.collections.get(target_name)

    # Handle name collision suffix (e.g. "MyColl.001")
    if linked_coll is None:
        candidates = [
            c for c in bpy.data.collections
            if c.name == target_name or c.name.startswith(target_name + ".")
        ]
        candidates.sort(key=lambda c: c.name)
        linked_coll = candidates[-1] if candidates else None

    if linked_coll is None:
        raise LoadError(
            f"wm.link completed but collection '{target_name}' not found in bpy.data.collections."
        )

    if linked_coll.name not in asset_container.children:
        asset_container.children.link(linked_coll)

    # ------------------------------------------------------------------
    # Keep original return semantics: return the (local) container collection in the scene.
    # Your original code returns asset_container, not the linked collection.
    # ------------------------------------------------------------------
    return asset_container


def get_collection(group_name):
    asset_container = bpy.data.collections.new(group_name)
    bpy.context.scene.collection.children.link(asset_container)

    return asset_container

