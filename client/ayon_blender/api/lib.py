import os
import traceback
import importlib
import contextlib
from typing import Dict, List, Union

import bpy
import addon_utils
from ayon_core.lib import (
    Logger,
    NumberDef
)
from ayon_core.pipeline import registered_host

from ayon_core.pipeline.create import CreateContext

from . import pipeline

from .constants import AYON_PROPERTY

log = Logger.get_logger(__name__)


def load_scripts(paths):
    """Copy of `load_scripts` from Blender's implementation.

    It is possible that this function will be changed in future and usage will
    be based on Blender version.

    This does not work in Blender 5+ due to `bpy_types` being unavailable. But
    usually this is not needed for Blender 5+ anyway, because it does allow
    better user scripts management through environment variables than older
    releases of Blender.
    """
    import bpy_types

    loaded_modules = set()

    previous_classes = [
        cls
        for cls in bpy.types.bpy_struct.__subclasses__()
    ]

    def register_module_call(mod):
        register = getattr(mod, "register", None)
        if register:
            try:
                register()
            except:  # noqa E722
                traceback.print_exc()
        else:
            print("\nWarning! '%s' has no register function, "
                  "this is now a requirement for registerable scripts" %
                  mod.__file__)

    def unregister_module_call(mod):
        unregister = getattr(mod, "unregister", None)
        if unregister:
            try:
                unregister()
            except:  # noqa E722
                traceback.print_exc()

    def test_reload(mod):
        # reloading this causes internal errors
        # because the classes from this module are stored internally
        # possibly to refresh internal references too but for now, best not to.
        if mod == bpy_types:
            return mod

        try:
            return importlib.reload(mod)
        except:  # noqa E722
            traceback.print_exc()

    def test_register(mod):
        if mod:
            register_module_call(mod)
            bpy.utils._global_loaded_modules.append(mod.__name__)

    from bpy_restrict_state import RestrictBlend

    with RestrictBlend():
        for base_path in paths:
            for path_subdir in bpy.utils._script_module_dirs:
                path = os.path.join(base_path, path_subdir)
                if not os.path.isdir(path):
                    continue

                bpy.utils._sys_path_ensure_prepend(path)

                # Only add to 'sys.modules' unless this is 'startup'.
                if path_subdir != "startup":
                    continue
                for mod in bpy.utils.modules_from_path(path, loaded_modules):
                    test_register(mod)

    addons_paths = []
    for base_path in paths:
        addons_path = os.path.join(base_path, "addons")
        if not os.path.exists(addons_path):
            continue
        addons_paths.append(addons_path)
        addons_module_path = os.path.join(addons_path, "modules")
        if os.path.exists(addons_module_path):
            bpy.utils._sys_path_ensure_prepend(addons_module_path)

    if addons_paths:
        # Fake addons
        origin_paths = addon_utils.paths

        def new_paths():
            paths = origin_paths() + addons_paths
            return paths

        addon_utils.paths = new_paths
        addon_utils.modules_refresh()

    # load template (if set)
    if any(bpy.utils.app_template_paths()):
        import bl_app_template_utils
        bl_app_template_utils.reset(reload_scripts=False)
        del bl_app_template_utils

    for cls in bpy.types.bpy_struct.__subclasses__():
        if cls in previous_classes:
            continue
        if not getattr(cls, "is_registered", False):
            continue
        for subcls in cls.__subclasses__():
            if not subcls.is_registered:
                print(
                    "Warning, unregistered class: %s(%s)" %
                    (subcls.__name__, cls.__name__)
                )


def append_user_scripts():
    """Apply user scripts to Blender.

    This was originally used for early Blender 4 versions due to requiring
    AYON to be sources from `BLENDER_USER_SCRIPTS` paths which unfortunately
    allowed only a single path, *and* it had the side effect of not loading the
    default user scripts anymore.

    In Blender 5+ this is irrelevant and instead additional Script Directories
    can be configured and used instead.
    """
    default_user_prefs = os.path.join(
        bpy.utils.resource_path('USER'),
        "scripts",
    )
    user_scripts = os.environ.get("AYON_BLENDER_USER_SCRIPTS") or default_user_prefs

    try:
        load_scripts(user_scripts.split(os.pathsep))
    except Exception:
        print("Couldn't load user scripts \"{}\"".format(user_scripts))
        traceback.print_exc()


def set_app_templates_path():
    # Blender requires the app templates to be in `BLENDER_USER_SCRIPTS`.
    # After running Blender, we set that variable to our custom path, so
    # that the user can use their custom app templates.

    # We look among the scripts paths for one of the paths that contains
    # the app templates. The path must contain the subfolder
    # `startup/bl_app_templates_user`.
    user_scripts = os.environ.get("AYON_BLENDER_USER_SCRIPTS")
    if not user_scripts:
        return

    paths = user_scripts.split(os.pathsep)
    app_templates_path = None
    for path in paths:
        if os.path.isdir(
                os.path.join(path, "startup", "bl_app_templates_user")):
            app_templates_path = path
            break

    if app_templates_path and os.path.isdir(app_templates_path):
        os.environ["BLENDER_USER_SCRIPTS"] = app_templates_path


def imprint(node: bpy.types.bpy_struct_meta_idprop, data: Dict):
    r"""Write `data` to `node` as userDefined attributes

    Arguments:
        node: Long name of node
        data: Dictionary of key/value pairs

    Example:
        >>> import bpy
        >>> def compute():
        ...   return 6
        ...
        >>> bpy.ops.mesh.primitive_cube_add()
        >>> cube = bpy.context.view_layer.objects.active
        >>> imprint(cube, {
        ...   "regularString": "myFamily",
        ...   "computedValue": lambda: compute()
        ... })
        ...
        >>> cube['ayon']['computedValue']
        6
    """

    imprint_data = dict()

    for key, value in data.items():
        if value is None:
            continue

        if callable(value):
            # Support values evaluated at imprint
            value = value()

        if not isinstance(value, (int, float, bool, str, list, dict)):
            raise TypeError(f"Unsupported type: {type(value)}")

        imprint_data[key] = value

    pipeline.metadata_update(node, imprint_data)


def lsattr(attr: str,
           value: Union[str, int, bool, List, Dict, None] = None) -> List:
    r"""Return nodes matching `attr` and `value`

    Arguments:
        attr: Name of Blender property
        value: Value of attribute. If none
            is provided, return all nodes with this attribute.

    Example:
        >>> lsattr("id", "myId")
        ...   [bpy.data.objects["myNode"]
        >>> lsattr("id")
        ...   [bpy.data.objects["myNode"], bpy.data.objects["myOtherNode"]]

    Returns:
        list
    """

    return lsattrs({attr: value})


def lsattrs(attrs: Dict) -> List:
    r"""Return nodes with the given attribute(s).

    Arguments:
        attrs: Name and value pairs of expected matches

    Example:
        >>> lsattrs({"age": 5})  # Return nodes with an `age` of 5
        # Return nodes with both `age` and `color` of 5 and blue
        >>> lsattrs({"age": 5, "color": "blue"})

    Returns a list.

    """

    # For now return all objects, not filtered by scene/collection/view_layer.
    matches = set()
    for coll in dir(bpy.data):
        if not isinstance(
                getattr(bpy.data, coll),
                bpy.types.bpy_prop_collection,
        ):
            continue
        for node in getattr(bpy.data, coll):
            ayon_prop = pipeline.get_ayon_property(node)
            if not ayon_prop:
                continue

            for attr, value in attrs.items():
                if (ayon_prop.get(attr)
                        and (value is None or ayon_prop.get(attr) == value)):
                    matches.add(node)
    return list(matches)


def read(node: bpy.types.bpy_struct_meta_idprop):
    """Return user-defined attributes from `node`"""

    data = dict(node.get(AYON_PROPERTY, {}))

    # Ignore hidden/internal data
    data = {
        key: value
        for key, value in data.items() if not key.startswith("_")
    }

    return data


def get_selected_collections():
    """
    Returns a list of the currently selected collections in the outliner.

    Raises:
        RuntimeError: If the outliner cannot be found in the main Blender
        window.

    Returns:
        list: A list of `bpy.types.Collection` objects that are currently
        selected in the outliner.
    """
    window = bpy.context.window or bpy.context.window_manager.windows[0]

    try:
        area = next(
            area for area in window.screen.areas
            if area.type == 'OUTLINER')
        region = next(
            region for region in area.regions
            if region.type == 'WINDOW')
    except StopIteration as e:
        raise RuntimeError("Could not find outliner. An outliner space "
                           "must be in the main Blender window.") from e

    with bpy.context.temp_override(
        window=window,
        area=area,
        region=region,
        screen=window.screen
    ):
        ids = bpy.context.selected_ids

    return [id for id in ids if isinstance(id, bpy.types.Collection)]


def get_selection(include_collections: bool = False) -> List[bpy.types.Object]:
    """
    Returns a list of selected objects in the current Blender scene.

    Args:
        include_collections (bool, optional): Whether to include selected
        collections in the result. Defaults to False.

    Returns:
        List[bpy.types.Object]: A list of selected objects.
    """
    selection = [obj for obj in bpy.context.scene.objects if obj.select_get()]

    if include_collections:
        selection.extend(get_selected_collections())

    return selection


@contextlib.contextmanager
def maintained_selection():
    r"""Maintain selection during context

    Example:
        >>> with maintained_selection():
        ...     # Modify selection
        ...     bpy.ops.object.select_all(action='DESELECT')
        >>> # Selection restored
    """

    previous_selection = get_selection()
    previous_active = bpy.context.view_layer.objects.active
    try:
        yield
    finally:
        # Clear the selection
        for node in get_selection():
            node.select_set(state=False)
        if previous_selection:
            for node in previous_selection:
                try:
                    node.select_set(state=True)
                except ReferenceError:
                    # This could happen if a selected node was deleted during
                    # the context.
                    log.exception("Failed to reselect")
                    continue
        try:
            bpy.context.view_layer.objects.active = previous_active
        except ReferenceError:
            # This could happen if the active node was deleted during the
            # context.
            log.exception("Failed to set active object.")


@contextlib.contextmanager
def maintained_time():
    """Maintain current frame during context."""
    current_time = bpy.context.scene.frame_current
    try:
        yield
    finally:
        bpy.context.scene.frame_current = current_time


def get_all_parents(obj):
    """Get all recursive parents of object.

    Arguments:
        obj (bpy.types.Object): Object to get all parents for.

    Returns:
        List[bpy.types.Object]: All parents of object

    """
    result = []
    while True:
        obj = obj.parent
        if not obj:
            break
        result.append(obj)
    return result


def get_highest_root(objects):
    """Get the highest object (the least parents) among the objects.

    If multiple objects have the same amount of parents (or no parents) the
    first object found in the input iterable will be returned.

    Note that this will *not* return objects outside of the input list, as
    such it will not return the root of node from a child node. It is purely
    intended to find the highest object among a list of objects. To instead
    get the root from one object use, e.g. `get_all_parents(obj)[-1]`

    Arguments:
        objects (List[bpy.types.Object]): Objects to find the highest root in.

    Returns:
        Optional[bpy.types.Object]: First highest root found or None if no
            `bpy.types.Object` found in input list.

    """
    included_objects = {obj.name_full for obj in objects}
    num_parents_to_obj = {}
    for obj in objects:
        if isinstance(obj, bpy.types.Object):
            parents = get_all_parents(obj)
            # included parents
            parents = [parent for parent in parents if
                       parent.name_full in included_objects]
            if not parents:
                # A node without parents must be a highest root
                return obj

            num_parents_to_obj.setdefault(len(parents), obj)

    if not num_parents_to_obj:
        return

    minimum_parent = min(num_parents_to_obj)
    return num_parents_to_obj[minimum_parent]


@contextlib.contextmanager
def attribute_overrides(
        obj,
        attribute_values
):
    """Apply attribute or property overrides during context.

    Supports nested/deep overrides, that is also why it does not use **kwargs
    as function arguments because it requires the keys to support dots (`.`).

    Example:
        >>> with attribute_overrides(scene, {
        ...     "render.fps": 30,
        ...     "frame_start": 1001}
        ... ):
        ...     print(scene.render.fps)
        ...     print(scene.frame_start)
        # 30
        # 1001

    Arguments:
        obj (Any): The object to set attributes and properties on.
        attribute_values: (dict[str, Any]): The property names mapped to the
            values that will be applied during the context.
    """
    if not attribute_values:
        # do nothing
        yield
        return

    # Helper functions to get and set nested keys on the scene object like
    # e.g. "scene.unit_settings.scale_length" or "scene.render.fps"
    # by doing `setattr_deep(scene, "unit_settings.scale_length", 10)`
    def getattr_deep(root, path):
        for key in path.split("."):
            root = getattr(root, key)
        return root

    def setattr_deep(root, path, value):
        keys = path.split(".")
        last_key = keys.pop()
        for key in keys:
            root = getattr(root, key)
        return setattr(root, last_key, value)

    # Get original values
    original = {
        key: getattr_deep(obj, key) for key in attribute_values
    }
    try:
        for key, value in attribute_values.items():
            setattr_deep(obj, key, value)
        yield
    finally:
        for key, value in original.items():
            setattr_deep(obj, key, value)


def collect_animation_defs(create_context, step=True, fps=False):
    """Get the basic animation attribute definitions for the publisher.

    Arguments:
        create_context (CreateContext): The context of publisher will be
            used to define the defaults for the attributes to use the current
            context's entity frame range as default values.
        step (bool): Whether to include `step` attribute definition.
        fps (bool): Whether to include `fps` attribute definition.

    Returns:
        List[NumberDef]: List of number attribute definitions.

    """

    # get scene values as defaults
    scene = bpy.context.scene
    # frame_start = scene.frame_start
    # frame_end = scene.frame_end
    # handle_start = 0
    # handle_end = 0

    # use task entity attributes to set defaults based on current context
    task_entity = create_context.get_current_task_entity()
    attrib: dict = task_entity["attrib"]
    frame_start = attrib["frameStart"]
    frame_end = attrib["frameEnd"]
    handle_start = attrib["handleStart"]
    handle_end = attrib["handleEnd"]

    # build attributes
    defs = [
        NumberDef("frameStart",
                  label="Frame Start",
                  default=frame_start,
                  decimals=0),
        NumberDef("frameEnd",
                  label="Frame End",
                  default=frame_end,
                  decimals=0),
        NumberDef("handleStart",
                  label="Handle Start",
                  tooltip="Frames added before frame start to use as handles.",
                  default=handle_start,
                  decimals=0),
        NumberDef("handleEnd",
                  label="Handle End",
                  tooltip="Frames added after frame end to use as handles.",
                  default=handle_end,
                  decimals=0),
    ]

    if step:
        defs.append(
            NumberDef(
                "step",
                label="Step size",
                tooltip="Number of frames to skip forward while rendering/"
                        "playing back each frame",
                default=1,
                decimals=0
            )
        )

    if fps:
        current_fps = scene.render.fps / scene.render.fps_base
        fps_def = NumberDef(
            "fps", label="FPS", default=current_fps, decimals=5
        )
        defs.append(fps_def)

    return defs


def get_cache_modifiers(obj, modifier_type="MESH_SEQUENCE_CACHE"):
    modifiers_dict = {}
    modifiers = [modifier for modifier in obj.modifiers
                 if modifier.type == modifier_type]
    if modifiers:
        modifiers_dict[obj.name] = modifiers
    else:
        for sub_obj in obj.children:
            for ob in sub_obj.children:
                cache_modifiers = [modifier for modifier in ob.modifiers
                                   if modifier.type == modifier_type]
                modifiers_dict[ob.name] = cache_modifiers
    return modifiers_dict


def get_blender_version():
    """Get Blender Version
    """
    major, minor, subversion = bpy.app.version
    return major, minor, subversion


@contextlib.contextmanager
def strip_container_data(containers):
    """Remove container data during context
    """
    container_data = {}
    for container in containers:
        node = container["node"]
        container_data[node] = dict(
            node.get(AYON_PROPERTY)
        )
        del node[AYON_PROPERTY]
    try:
        yield

    finally:
        for key, item in container_data.items():
            key[AYON_PROPERTY] = item


@contextlib.contextmanager
def strip_instance_data(node):
    """Remove instance data during context
    """
    previous_data = dict(node.get(AYON_PROPERTY, {}))
    try:
        node[AYON_PROPERTY]["active"] = False
        yield
    finally:
        node[AYON_PROPERTY] = previous_data


@contextlib.contextmanager
def strip_namespace(containers):
    """Strip namespace during context
    This context manager is only valid for blender version elder than 5.0.
    This would be deprecated after the blender 5.0.
    """
    if get_blender_version() >= (5, 0, 0):
        yield
        return

    nodes = [
        container["node"] for container in containers
    ]
    original_namespaces = {}
    for node in nodes:
        if isinstance(node, bpy.types.Collection):
            children = node.children_recursive
        elif isinstance(node, bpy.types.Object):
            children = node.children
        elif isinstance(node, (bpy.types.Node, bpy.types.Action)):
            children = [node]
        else:
            raise TypeError(f"Unsupported type: {node} ({type(node)})")

        for child in children:
            original_name = child.name
            if ":" not in original_name:
                continue
            namespace, name = original_name.rsplit(':', 1)
            child.name = name
            original_namespaces[child] = namespace

    try:
        yield
    finally:
        for node, original_namespace in original_namespaces.items():
            node.name = f"{original_namespace}:{name}"


@contextlib.contextmanager
def packed_images(datablocks, logger=None):
    """Unpack packed images during context
    This will pack all unpacked images found in the given datablocks,
    and unpack them back when exiting the context.

    Args:
        datablocks (set): Datablocks to search for
            unpacked images.
        logger (logging.Logger): Logger to use for warnings if packing fails.

    """

    if logger is None:
        logger = log

    unpacked_node_images = set()
    for data in datablocks:
        if not (
            isinstance(data, bpy.types.Object) and data.type == 'MESH'
        ):
            continue
        for material_slot in data.material_slots:
            mat = material_slot.material
            if not (mat and mat.use_nodes):
                continue
            tree = mat.node_tree
            if tree.type != 'SHADER':
                continue
            for node in tree.nodes:
                if node.bl_idname != 'ShaderNodeTexImage':
                    continue
                if not node.image:
                    continue
                if node.image.packed_file is not None:
                    continue

                try:
                    node.image.pack()
                except RuntimeError:
                    logger.warning(
                        f"Unable to pack node: {node}",
                        exc_info=True
                    )
                    continue
                unpacked_node_images.add(node.image)
    try:
        yield

    finally:
        for image in unpacked_node_images:
            image.unpack()


def search_replace_render_paths(src: str, dest: str) -> bool:
    """Search and replace render paths in the current scene.

    This function searches for all render paths in the current scene and
    replaces them with a new path defined by the user.

    Arguments:
        src (str): Search text to replace.
        dest (str): Replacement text for the search.

    Returns:
        bool: True if any changes were made, False otherwise.

    """
    changes = False

    # Scene
    path: str = bpy.context.scene.render.filepath
    new_path: str = path.replace(src, dest)
    if new_path != path:
        log.info(f"Updating scene render path from '{path}' to '{new_path}'")
        bpy.context.scene.render.filepath = new_path
        changes = True

    # Base paths for Compositor File Output Nodes
    node_tree = get_scene_node_tree()
    if node_tree:
        for node in node_tree.nodes:
            if node.bl_idname != "CompositorNodeOutputFile":
                continue

            path: str = node.base_path
            new_path: str = path.replace(src, dest)
            if new_path == path:
                continue

            log.info(
                "Updating compositor output file node base render path from "
                f"'{path}' to '{new_path}'"
            )
            node.base_path = new_path
            changes = True

    return changes


def get_scene_node_tree(ensure_exists=False):
    """Return the node tree

    Arguments:
        ensure_exists (bool): When enabled, make sure a compositor node tree is
            enabled and set.
    """
    if get_blender_version() >= (5, 0, 0):
        # Blender 5.0+
        if not bpy.context.scene.compositing_node_group and ensure_exists:
            # In Blender 5 if no comp node tree is set, create one
            tree = bpy.data.node_groups.new("Compositor Nodes",
                                            "CompositorNodeTree")
            bpy.context.scene.compositing_node_group = tree
            return tree

        return bpy.context.scene.compositing_node_group
    else:
        # Blender 4.0 and below
        if not bpy.context.scene.node_tree and ensure_exists:
            # Force enable compositor in Blender 4
            bpy.context.scene.use_nodes = True

        return bpy.context.scene.node_tree


def create_animation_instance(rig: Union[bpy.types.Collection, bpy.types.Object]):
    """Create animation instances for the given rigs.

    Args:
        rig (Union[bpy.types.Collection, bpy.types.Object]): Rig to create
        animation instances for.
    """
    creator_identifier = "io.ayon.creators.blender.animation"
    host = registered_host()
    create_context = CreateContext(host)

    create_context.create(
        creator_identifier=creator_identifier,
        variant=rig.name.split(':')[-1],
        pre_create_data={
            "use_selection": False,
            "asset_group": rig
        }
    )
