"""Load an asset in Blender from an Alembic file."""

from pathlib import Path
from typing import Dict, List, Optional, Union

import bpy

from ayon_core.lib import BoolDef
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


class ObjectPathMatcher:
    """Build a lookup to find the longest matching suffix of an object path
    among a large list of object paths.

    The lookup helps because we may be doing a large number of lookups to the
    same set of object paths.
    """
    def __init__(self, object_paths: list[str]):
        self._lookup: dict[tuple[str, ...], str] = {}
        self._object_paths: list[str] = [str(p) for p in object_paths]
        self._is_dirty: bool = True

    def _build_lookup(self):
        # Reverse so first objects are added to the lookup last and thus are
        # found first in case of multiple matches
        for path in reversed(self._object_paths):
            parts = path.split("/")
            for i in range(len(parts)):
                self._lookup[tuple(parts[i:])] = path
        self._is_dirty = False

    def find_best_match(self, path: str) -> Optional[str]:
        """Return best match with the longest matching suffix in the lookup."""
        if self._is_dirty:
            self._build_lookup()
        parts = path.split("/")
        for i in range(len(parts)):
            key  = tuple(parts[i:])
            match = self._lookup.get(key, None)
            if match is not None:
                return match
        return None


class CacheModelLoader(plugin.BlenderLoader):
    """Load cache models.

    Stores the imported asset in a collection named after the asset.

    Note:
        At least for now it only supports Alembic files.
    """
    product_base_types = {"*"}
    product_types = product_base_types
    representations = {"*"}
    extensions = {"abc", "usd", "usda", "usdc", "usdz", "obj"}

    label = "Load Cache"
    icon = "code-fork"
    color = "orange"

    always_add_cache_reader = False
    add_namespace = True

    @classmethod
    def get_options(cls, contexts):
        return [
            BoolDef("always_add_cache_reader",
                    default=cls.always_add_cache_reader,
                    label="Always Add Cache Reader (Alembic)"),
            BoolDef("add_namespace",
                    default=cls.add_namespace,
                    label="Add namespace to objects"),
        ]

    def _update_transform_cache_path(self, asset_group, libpath):
        """search and update path in the transform cache modifier
        If there is no transform cache modifier, it will create one
        to update the filepath of the alembic.
        """
        # Load new cache file
        new_cachefile = lib.add_cache_file(libpath.as_posix())
        # set scale to 1.0 to avoid transform cache defaulting to 0 scale
        new_cachefile.scale = 1.0

        remove_caches = set()
        datablock_object_paths: Dict[
            Union[
                bpy.types.MeshCacheModifier,
                bpy.types.TransformCacheConstraint
            ],
            str
        ] = {}
        to_update: list[
            Union[
                bpy.types.MeshCacheModifier,
                bpy.types.TransformCacheConstraint
            ]
        ] = []
        for obj in asset_group.children_recursive:
            # TODO: The user may have parented other objects under the asset
            #  group that may not be related to this cache file. We should
            #  find a better way to identify the correct objects to update.
            # Find all datablocks to update cache file for and update the
            # object path attribute for.
            to_update.extend(
                modifier for modifier in obj.modifiers
                if modifier.type == "MESH_SEQUENCE_CACHE"
            )
            to_update.extend(
                constraint for constraint in obj.constraints
                if constraint.type == "TRANSFORM_CACHE"
            )

        for datablock in to_update:
            if not datablock.cache_file:
                continue
            remove_caches.add(datablock.cache_file)
            datablock.cache_file = new_cachefile
            datablock_object_paths[datablock] = datablock.object_path

            # Temporarily clear the old object path just to avoid Blender's
            # Alembic reader to spew out errors during the update. For paths
            # that are not found in the new cache file but for whom we are able
            # to find a replacement.
            datablock.object_path = ""

        # The new cache file does not return any `object_paths` unless it is
        # currently applied to a modifier or constraint that gets evaluated
        # in the depsgraph. So it needs to be assigned before we call this
        # reload method. The alternative is to call
        # `bpy.context.evaluated_depsgraph_get()` but that also only works
        # if assigned to a scene object. Otherwise, both would
        # always return an empty list directly after load.
        bpy.ops.cachefile.reload()

        # Start updating object paths that are not 1:1 found in new cache
        # file. Like objects that may have moved in a hierarchy. New objects
        # or objects that have been removed or renamed cannot be matched.
        new_object_paths = [
            object_path.path for object_path in new_cachefile.object_paths
        ]
        object_path_matcher = ObjectPathMatcher(new_object_paths)

        def _match_object_path(object_path) -> Optional[str]:
            if object_path not in new_cachefile.object_paths:
                new_path = object_path_matcher.find_best_match(object_path)
                if new_path is not None:
                    self.log.info(
                        "Updating object path:\n"
                        "- %s   <- before\n"
                        "- %s   <- after",
                        object_path,
                        new_path
                    )
                    return new_path
                else:
                    self.log.warning(
                        "Missing object path '%s' in cache "
                        "file: %s", object_path, new_cachefile.filepath
                    )
                    return None
            return object_path

        for datablock, old_object_path in datablock_object_paths.items():
            new_object_path = _match_object_path(old_object_path)
            if new_object_path:
                datablock.object_path = new_object_path
            else:
                # Path is missing in the new cache file, keep the old path
                # just to keep a trace of the missing paths, e.g. for when
                # updating back to the old version
                datablock.object_path = old_object_path

        # Remove dangling cache files that are not used anymore
        remove_caches = {
            cache for cache in remove_caches
            if not lib.has_users(cache)
        }

        if remove_caches:
            bpy.data.batch_remove(remove_caches)

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

    def _process(self, libpath, asset_group, group_name, options: Dict):
        if options is None:
            options = {}

        plugin.deselect_all()

        relative = bpy.context.preferences.filepaths.use_relative_paths

        if any(libpath.lower().endswith(ext)
               for ext in [".usd", ".usda", ".usdc", ".usdz"]):
            # USD
            bpy.ops.wm.usd_import(
                filepath=libpath,
                relative_path=relative
            )
        elif libpath.lower().endswith(".obj"):
            # OBJ
            bpy.ops.wm.obj_import(filepath=libpath)
        else:
            # Alembic
            always_add_cache_reader = options.get(
                "always_add_cache_reader",
                self.always_add_cache_reader
            )
            bpy.ops.wm.alembic_import(
                filepath=libpath,
                relative_path=relative,
                always_add_cache_reader=always_add_cache_reader
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

            if options.get("add_namespace", self.add_namespace):
                obj.name = f"{group_name}:{name}"
                if obj.type != 'EMPTY':
                    name_data = obj.data.name
                    obj.data.name = f"{group_name}:{name_data}"

                    for material_slot in obj.material_slots:
                        name_mat = material_slot.material.name
                        material_slot.material.name = (
                            f"{group_name}:{name_mat}"
                        )

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
        objects = self._process(libpath, asset_group, group_name, options)

        # Link the asset group to the active collection
        collection = bpy.context.view_layer.active_layer_collection.collection
        collection.objects.link(asset_group)
        container = get_ayon_container()
        self._link_objects(objects, asset_group, container)

        asset_group[AYON_PROPERTY] = {
            "schema": "ayon:container-3.0",
            "id": AYON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
            "project_name": context["project"]["name"],
            # Blender-specific metadata
            "libpath": libpath,
            "asset_name": asset_name,
            "objectName": group_name,
            "options": options or {}
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

        if extension in {".usd", ".usda", ".usdc"}:
            # Special behavior for USD files
            options = container.get("options", {})
            mat = asset_group.matrix_basis.copy()
            self._remove(asset_group)

            objects = self._process(str(libpath), asset_group, object_name, options)

            container = get_ayon_container()
            self._link_objects(objects, asset_group, container)

            asset_group.matrix_basis = mat
        else:
            self._update_transform_cache_path(asset_group,
                                              libpath)

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
