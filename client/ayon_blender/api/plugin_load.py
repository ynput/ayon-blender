import logging
from typing import Generator, TYPE_CHECKING

import bpy
from ayon_core.pipeline.load import LoadError
# from typing import Union, Iterable


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
    # Pre 4.0 method:
    else:
        pass

    scene.collection.children.unlink(loaded_collection)

    local_collection = get_local_collection(
        overridden_collections,
        loaded_collection,
    )
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


def load_collection(
    filepath,
    link=True,
    lib_container_name = None
) -> bpy.types.Collection:
    """Load a collection to the scene."""
    with bpy.data.libraries.load(filepath, link=link, relative=False) as (
        data_from,
        data_to,
    ):
        if lib_container_name is None:
            lib_container_name = data_from.collections[0]

        data_to.collections = [lib_container_name]
    loaded_containers = data_to.collections

    if len(loaded_containers) != 1:
        for loaded_container in loaded_containers:
            bpy.data.collections.remove(loaded_container)
        raise LoadError(
            "More then 1 'container' is loaded. That means the publish was "
            "not correct."
        )
    container_collection = loaded_containers[0]

    return container_collection


# def add_asset_to_group(
#     asset: dict, data_block: Union[bpy.types.Collection, bpy.types.Object]
# ) -> None:
#     """Group an asset according to the asset type.
#     """
#     asset_type = asset["data"]["group"].lower()
#     group_hierarchy = (asset_type,)
#     scene = bpy.context.scene
#     if group_hierarchy:
#         group_data_block(
#             data_block,
#             group_hierarchy,
#         )
#         if isinstance(data_block, bpy.types.Collection):
#             try:
#                 scene.collection.children.unlink(data_block)
#             except RuntimeError:
#                 # The collection wasn't a child of the scene collection
#                 pass
#         if isinstance(data_block, bpy.types.Object):
#             try:
#                 scene.collection.objects.unlink(data_block)
#             except RuntimeError:
#                 # The object wasn't part of the scene collection
#                 pass


# def group_data_block(
#     data_block: Union[bpy.types.Collection, bpy.types.Object],
#     group_hierarchy: Iterable[str],
# ) -> list[bpy.types.Collection]:
#     """Link the collection or object under parent collections.

#     Arguments:
#         data_block: The collection or object to group.

#         group_hierarchy: The group collections to use for grouping. The first one will
#             be the top parent with every next one as child and the given collection or
#             object will be the last child. E.g.:

#             .. code::

#                 animation
#                     └── character
#                         └── data block

#     Returns:
#         The group collections, starting with the top parent.

#     Example:
#         >>> group_data_block(my_asset, ("animation", "prop"))
#         [bpy.data.collections['animation'], bpy.data.collections['character']]
#     """
#     parent_collections = []
#     parent = None
#     for group_name in group_hierarchy:
#         group_collection = _get_group_collection(group_name)
#         _group_under(group_collection, parent)
#         parent_collections.append(group_collection)
#         # Set the group collection as parent for the next one.
#         parent = group_collection

#     if not parent:
#         return parent_collections

#     if isinstance(data_block, bpy.types.Collection):
#         if not _is_child_of(parent, data_block):
#             parent.children.link(data_block)
#     if isinstance(data_block, bpy.types.Object):
#         if not _is_child_of(parent, data_block):
#             parent.objects.link(data_block)
#     return parent_collections