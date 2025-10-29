from typing import Dict, List, Optional

import bpy

from ayon_core.pipeline import AYON_CONTAINER_ID

from ayon_blender.api.constants import AYON_PROPERTY
from ayon_blender.api import plugin


def get_users(ID):
    """Yield all users"""
    if not ID.users:
        return

    for attr in dir(bpy.data):
        data = getattr(bpy.data, attr, None)
        if not isinstance(data, bpy.types.bpy_prop_collection):
            continue

        for obj in data:
            if obj.user_of_id(ID):
                yield obj


class CacheDataLoader(plugin.BlenderLoader):
    """Load Alembic cache as a managed CacheFile datablock."""
    product_types = {"*"}
    representations = {"abc"}

    label = "Load Cache Data"
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
        filepath = self.filepath_from_context(context)
        relative = bpy.context.preferences.filepaths.use_relative_paths

        before_cachefiles = set(bpy.data.cache_files)
        bpy.ops.wm.alembic_import(
            filepath=filepath,
            relative_path=relative,
            # Always add constraint and cache reader, even if not animated,
            # so that if we update later that they will be animated when
            # animated then. This also makes it so that transforms for
            # non-animated objects would update too if the transform
            # differs in the new version.
            always_add_cache_reader=True
        )
        cachefile = next(cache for cache in bpy.data.cache_files
                         if cache not in before_cachefiles)

        plugin.deselect_all()

        self._imprint(cachefile, context)

        return [cachefile]

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset."""
        cache_file: "bpy.types.CacheFile" = container["node"]
        cache_file.filepath = self.filepath_from_context(context)

        # TODO: On update, add missing geometry
        # Detect any object paths in the cache file that are not used. For
        # those, generate the relevant objects
        # for object_path in cache_file.object_paths:

        # Update representation id
        cache_file[AYON_PROPERTY]["representation"] = (
            context["representation"]["id"])

    def exec_remove(self, container: Dict) -> bool:
        """Remove an existing container from a Blender scene."""
        datablock = container["node"]

        users = list(get_users(datablock))
        bpy.data.batch_remove([datablock] + users)
        return True

    def _imprint(self, cache_file: "bpy.types.CacheFile", context):
        cache_file[AYON_PROPERTY] = {
            "schema": "ayon:container-3.0",
            "id": AYON_CONTAINER_ID,
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],

            # Metadata to visualize in UIs
            # TODO: Preferably we keep this name and metadata live to the
            #  object instead of imprinting it as attributes so that UIs would
            #  always display the live values
            "name": cache_file.name_full,
            "namespace": cache_file.name,
        }
