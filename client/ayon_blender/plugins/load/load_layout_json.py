"""Load a layout in Blender."""

import json
import math
from pathlib import Path
from pprint import pformat
from typing import Dict, Optional

import bpy
import ayon_api
from mathutils import Euler, Matrix, Vector

from ayon_core.pipeline import (
    discover_loader_plugins,
    remove_container,
    load_container,
    loaders_from_representation,
    AYON_CONTAINER_ID,
)
from ayon_blender.api.constants import (
    AYON_INSTANCES,
    AYON_PROPERTY,
    VALID_EXTENSIONS
)
from ayon_blender.api import plugin
from ayon_blender.api.lib import assign_action
from ayon_blender.api.ops import MainThreadItem, execute_in_main_thread
from ayon_blender.api.pipeline import add_to_ayon_container


class JsonLayoutLoader(plugin.BlenderLoader):
    """Load layout published from Unreal."""

    product_base_types = {"layout"}
    product_types = product_base_types
    representations = {"*"}
    extensions = {"json"}

    label = "Load Layout"
    icon = "code-fork"
    color = "orange"

    def _remove(self, asset_group):
        objects = list(asset_group.children)

        for obj in objects:
            remove_container(obj.get(AYON_PROPERTY))

    def _remove_animation_instances(self, asset_group):
        instances = bpy.data.collections.get(AYON_INSTANCES)
        if instances:
            anim_collections = set()
            for obj in asset_group.children:
                anim_collection = instances.children.get(
                    obj.name + "_animation")
                if anim_collection:
                    anim_collections.add(anim_collection)
            bpy.data.batch_remove(anim_collections)

    def _get_loader(self, loaders, product_base_type):
        # The loaders are already filtered by the element's product base type
        # and representation. Prefer the Append Blend loader: it handles every
        # product base type that can be part of a layout (model, rig, camera,
        # layout, animation) and loads each element as its own container.
        if not loaders:
            return None

        for loader in loaders:
            if loader.__name__ == "BlendLoader":
                return loader

        return loaders[0]

    def _get_animation_file(self, libpath, element):
        """Return the baked animation file of a layout element, if any.

        Newer layouts publish the FBX next to the layout JSON as
        ``<json stem>.fbx``. Layouts published before that stored the staging
        file name (e.g. ``000.fbx``) and were published as
        ``<json stem>.000.fbx``, so both are supported.
        """
        animation = element.get("animation")
        if not animation:
            return None

        json_path = Path(libpath)
        stem = json_path.with_suffix("")
        for candidate in (Path(f"{stem}.fbx"), Path(f"{stem}.{animation}")):
            if candidate.is_file():
                return str(candidate)

        # Fall back to a single FBX next to the layout JSON
        fbx_files = list(json_path.parent.glob("*.fbx"))
        if len(fbx_files) == 1:
            return str(fbx_files[0])

        self.log.warning(
            "Layout element '%s' has animation '%s', but no animation file "
            "was found next to '%s'.",
            element.get("instance_name") or element.get("asset_name"),
            animation, libpath
        )
        return None

    @staticmethod
    def _get_reference(element):
        """Return the representation id of the layout element.

        Blender layouts store it as `reference` (the blend representation of
        the element). Layouts published from other hosts (Maya, Houdini,
        Unreal) store the representation that was loaded there in
        `representation`.
        """
        return (
            element.get("reference")
            or element.get("representation")
            or element.get("reference_fbx")
            or element.get("reference_abc")
        )

    def _get_transform(self, element):
        """Return the location, rotation and scale of a layout element.

        Blender layouts store the transform as `translation`, `rotation` and
        `scale`. Layouts from other hosts only store `transform_matrix` in
        Unreal's convention, which is converted to Blender here.
        """
        transform = element.get("transform")
        if transform:
            return transform

        matrix = element.get("transform_matrix")
        if not matrix:
            return None
        try:
            return self._transform_from_unreal_matrix(matrix)
        except (TypeError, ValueError):
            self.log.warning(
                "Unable to convert the transform matrix of layout element "
                "'%s': %r",
                element.get("instance_name") or element.get("asset_name"),
                matrix, exc_info=True
            )
            return None

    @staticmethod
    def _transform_from_unreal_matrix(matrix):
        """Convert an Unreal convention layout matrix to Blender values.

        Layout matrices of other hosts (e.g. Maya's Extract Layout) are
        written in Unreal's coordinate system. Unreal maps to the Y-up hosts
        (Maya, Houdini) by swapping the Y and Z components, so that swap is
        undone first. The resulting Y-up values are then converted to
        Blender's Z-up coordinate system.
        """
        # Layout matrices are stored for row vectors, while Blender uses
        # column vectors, so transpose the matrix.
        unreal = Matrix(matrix).transposed()

        location, rotation, scale = unreal.decompose()
        euler = rotation.to_euler("XYZ")

        # Unreal -> Y-up (Maya/Houdini)
        location = Vector((location.x, location.z, location.y))
        scale = Vector((scale.x, scale.z, scale.y))
        euler = Euler((euler.x, euler.z, euler.y), "XYZ")

        # Y-up -> Blender's Z-up
        convert = Matrix.Rotation(math.radians(90.0), 3, "X")
        location = convert @ location
        scale = Vector((scale.x, scale.z, scale.y))
        rotation = convert @ euler.to_matrix() @ convert.transposed()
        euler = rotation.to_euler("XYZ")

        return {
            "translation": {
                "x": location.x, "y": location.y, "z": location.z
            },
            "rotation": {
                "x": euler.x, "y": euler.y, "z": euler.z
            },
            "scale": {
                "x": scale.x, "y": scale.y, "z": scale.z
            },
        }

    def _process(self, libpath, asset, asset_group, actions):
        plugin.deselect_all()

        with open(libpath, "r") as fp:
            data = json.load(fp)

        if not isinstance(data, list):
            self.log.warning(
                "Layout '%s' does not contain a list of elements.", libpath
            )
            return

        all_loaders = discover_loader_plugins()
        loaded_elements = 0
        pending = []

        for element in data:
            if not isinstance(element, dict):
                self.log.warning(
                    "Skipping invalid layout element: %r", element
                )
                continue

            reference = self._get_reference(element)
            instance_name = element.get('instance_name')
            product_base_type = (
                element.get("product_base_type")
                or element.get("product_type")
                or element.get("family")
            )

            if not reference:
                self.log.warning(
                    "Layout element '%s' has no representation reference; "
                    "skipping it.",
                    instance_name or element.get("asset_name")
                )
                continue

            loaders = loaders_from_representation(all_loaders, reference)
            loader = self._get_loader(loaders, product_base_type)

            if not loader:
                self.log.warning(
                    "No loader found for layout element '%s' (product base "
                    "type '%s'); skipping it.",
                    instance_name or element.get("asset_name"),
                    product_base_type
                )
                continue

            action = None

            if actions:
                action = actions.get(instance_name, None)

            pending.append({
                "namespace": instance_name,
                "transform": self._get_transform(element),
                "action": action,
                "animation_file": (
                    None if action
                    else self._get_animation_file(libpath, element)
                ),
            })

            # This should return the loaded asset, but the load call will be
            # added to the queue to run in the Blender main thread, so
            # at this time it will not return anything. The assets are loaded
            # in the next Blender cycle, so the parent, transform, action and
            # baked animation are applied by the follow-up item queued below.
            load_container(
                loader,
                reference,
                namespace=instance_name
            )
            loaded_elements += 1

        if pending:
            # The element loads are queued on the Blender main thread, so the
            # layout data is applied as a follow-up item, after they are done.
            execute_in_main_thread(MainThreadItem(
                self._apply_elements, asset_group, pending
            ))

        if not data:
            self.log.warning("Layout '%s' contains no elements.", libpath)
        elif not loaded_elements:
            self.log.warning(
                "None of the %d elements of layout '%s' could be loaded.",
                len(data), libpath
            )

        # Camera creation when loading a layout is not necessary for now,
        # but the code is worth keeping in case we need it in the future.
        # # Create the camera asset and the camera instance
        # creator_plugin = get_legacy_creator_by_name("CreateCamera")
        # if not creator_plugin:
        #     raise ValueError("Creator plugin \"CreateCamera\" was "
        #                      "not found.")

        # TODO: Refactor legacy create usage to new style creators
        # legacy_create(
        #     creator_plugin,
        #     name="camera",
        #     # name=f"{unique_number}_{product[name]}_animation",
        #     asset=asset,
        #     options={"useSelection": False}
        #     # data={"dependencies": context["representation"]["id"]}
        # )

    def _apply_elements(self, asset_group, elements):
        """Apply the layout data to the loaded element containers.

        This runs on the Blender main thread after the element loads were
        queued, so the loaded element containers exist by then. It applies
        the parent, transform, action and baked animation of every element,
        independent of the loader that loaded the element.
        """
        containers_by_namespace = {}
        for obj in bpy.data.objects:
            metadata = obj.get(AYON_PROPERTY)
            if not metadata:
                continue
            namespace = metadata.get("namespace")
            if namespace:
                containers_by_namespace.setdefault(namespace, obj)

        for element in elements:
            namespace = element["namespace"]
            container = containers_by_namespace.get(namespace)
            if container is None:
                self.log.warning(
                    "Unable to apply layout element '%s': it was not loaded.",
                    namespace
                )
                continue

            container.parent = asset_group

            transform = element.get("transform")
            if transform:
                for attr, key in (
                    ("location", "translation"),
                    ("rotation_euler", "rotation"),
                    ("scale", "scale"),
                ):
                    values = transform.get(key)
                    if values:
                        setattr(
                            container, attr,
                            (values["x"], values["y"], values["z"])
                        )

            action = element.get("action")
            if action:
                for obj in container.children_recursive:
                    if obj.type != "ARMATURE":
                        continue
                    assign_action(obj, action)
                continue

            animation_file = element.get("animation_file")
            if animation_file:
                self._apply_animation_file(container, animation_file)

    def _apply_animation_file(self, container, filepath):
        """Apply the animation baked into a layout element's FBX file.

        Layout publishes bake the rig animation into an FBX next to the
        layout JSON. The action is moved onto the armature of the loaded rig,
        after which the objects imported from the FBX are removed again.
        """
        filepath = Path(filepath)
        if not filepath.is_file():
            self.log.warning(
                "Unable to apply animation: '%s' does not exist.", filepath
            )
            return

        armatures = [
            obj for obj in container.children_recursive
            if obj.type == 'ARMATURE'
        ]
        if not armatures:
            self.log.warning(
                "Unable to apply animation '%s': no armature found in '%s'.",
                filepath, container.name
            )
            return

        objects_before = set(bpy.data.objects)
        actions_before = set(bpy.data.actions)
        try:
            bpy.ops.import_scene.fbx(
                filepath=str(filepath), use_anim=True
            )
        except (RuntimeError, AttributeError):
            self.log.warning(
                "Unable to import animation file '%s'.",
                filepath, exc_info=True
            )
            return

        imported_objects = set(bpy.data.objects) - objects_before
        imported_actions = set(bpy.data.actions) - actions_before

        armatures_by_name = {
            armature.name.rsplit(":", 1)[-1]: armature
            for armature in armatures
        }

        applied_actions = set()
        for imported in imported_objects:
            if imported.type != 'ARMATURE':
                continue
            imported_animation = imported.animation_data
            if not imported_animation or not imported_animation.action:
                continue
            action = imported_animation.action
            target = armatures_by_name.get(imported.name)
            if target is None and len(armatures) == 1:
                target = armatures[0]
            if target is None:
                continue
            assign_action(target, action)
            applied_actions.add(action)

        # Remove the objects imported from the FBX, but keep the actions that
        # were applied to the loaded rig.
        to_remove = set(imported_objects)
        for imported in imported_objects:
            data = imported.data
            if data is not None and data.users <= 1:
                to_remove.add(data)
        bpy.data.batch_remove(to_remove)

        for action in imported_actions - applied_actions:
            if action.users == 0:
                bpy.data.actions.remove(action)

    def process_asset(self,
                      context: dict,
                      name: str,
                      namespace: Optional[str] = None,
                      options: Optional[Dict] = None):
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

        self._process(libpath, asset_name, asset_group, None)

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
            "project_name": context["project"]["name"],
            "objectName": group_name,
        }

        self[:] = asset_group.children
        return asset_group.children

    def exec_update(self, container: Dict, context: Dict):
        """Update the loaded asset.

        This will remove all objects of the current collection, load the new
        ones and add them to the collection.
        If the objects of the collection are used in another collection they
        will not be removed, only unlinked. Normally this should not be the
        case though.
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

        actions = {}

        repre_ids = set()
        for obj in asset_group.children:
            obj_meta = obj.get(AYON_PROPERTY)
            repre_id = obj_meta.get("representation")
            if repre_id:
                repre_ids.add(repre_id)

        project_name = context["project"]["name"]
        hierarchy_by_repre_id = ayon_api.get_representations_hierarchy(
            project_name,
            repre_ids,
            project_fields=[],
            folder_fields=[],
            task_fields=[],
            product_fields={"productBaseType"},
            version_fields=[],
            representation_fields={"id"},
        )

        for obj in asset_group.children:
            obj_meta = obj.get(AYON_PROPERTY)
            repre_id = obj_meta.get("representation")
            hierarchy = hierarchy_by_repre_id.get(repre_id)
            if not hierarchy:
                continue
            product_base_type = hierarchy.product["productBaseType"]
            if product_base_type == "rig":
                rig = None
                for child in obj.children:
                    if child.type == 'ARMATURE':
                        rig = child
                        break
                if not rig:
                    raise Exception("No armature in the rig asset group.")
                if rig.animation_data and rig.animation_data.action:
                    namespace = obj_meta.get('namespace')
                    actions[namespace] = rig.animation_data.action

        mat = asset_group.matrix_basis.copy()

        self._remove_animation_instances(asset_group)

        self._remove(asset_group)

        self._process(
            str(libpath), metadata["asset_name"], asset_group, actions
        )

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
        """
        object_name = container["objectName"]
        asset_group = bpy.data.objects.get(object_name)

        if not asset_group:
            return False

        self._remove_animation_instances(asset_group)

        self._remove(asset_group)

        bpy.data.objects.remove(asset_group)

        return True
