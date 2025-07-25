import os
import sys
import traceback
from typing import Callable, Dict, Iterator, List, Optional, Union

import bpy

import pyblish.api

from ayon_core.host import (
    HostBase,
    IWorkfileHost,
    IPublishHost,
    ILoadHost
)
from ayon_core.pipeline import (
    schema,
    register_loader_plugin_path,
    register_creator_plugin_path,
    deregister_loader_plugin_path,
    deregister_creator_plugin_path,
    AYON_CONTAINER_ID,
    AVALON_CONTAINER_ID,
    get_current_project_name
)
from ayon_core.pipeline.context_tools import (
    get_current_task_entity
)
from ayon_core.lib import (
    Logger,
    register_event_callback,
    emit_event,
    filter_profiles
)
from ayon_core.settings import get_project_settings
from ayon_blender import BLENDER_ADDON_ROOT

from . import lib
from . import ops

from .constants import (
    AVALON_INSTANCES,
    AYON_INSTANCES,
    AVALON_CONTAINERS,
    AYON_CONTAINERS,
    AVALON_PROPERTY,
    AYON_PROPERTY,
    IS_HEADLESS
)
from .lib import search_replace_render_paths

from .workio import (
    open_file,
    save_file,
    current_file,
    has_unsaved_changes,
    file_extensions,
    work_root,
)

PLUGINS_DIR = os.path.join(BLENDER_ADDON_ROOT, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "create")

ORIGINAL_EXCEPTHOOK = sys.excepthook


log = Logger.get_logger(__name__)


class BlenderHost(HostBase, IWorkfileHost, IPublishHost, ILoadHost):
    name = "blender"

    def install(self):
        """Override install method from HostBase.
        Install Blender host functionality."""
        install()

    def get_containers(self) -> Iterator:
        """List containers from active Blender scene."""
        return ls()

    def get_workfile_extensions(self) -> List[str]:
        """Override get_workfile_extensions method from IWorkfileHost.
        Get workfile possible extensions.

        Returns:
            List[str]: Workfile extensions.
        """
        return file_extensions()

    def save_workfile(self, dst_path: str = None):
        """Override save_workfile method from IWorkfileHost.
        Save currently opened workfile.

        Args:
            dst_path (str): Where the current scene should be saved. Or use
                current path if `None` is passed.
        """
        save_file(dst_path if dst_path else bpy.data.filepath)

    def open_workfile(self, filepath: str):
        """Override open_workfile method from IWorkfileHost.
        Open workfile at specified filepath in the host.

        Args:
            filepath (str): Path to workfile.
        """
        open_file(filepath)

    def get_current_workfile(self) -> str:
        """Override get_current_workfile method from IWorkfileHost.
        Retrieve currently opened workfile path.

        Returns:
            str: Path to currently opened workfile.
        """
        return current_file()

    def workfile_has_unsaved_changes(self) -> bool:
        """Override wokfile_has_unsaved_changes method from IWorkfileHost.
        Returns True if opened workfile has no unsaved changes.

        Returns:
            bool: True if scene is saved and False if it has unsaved
                modifications.
        """
        return has_unsaved_changes()

    def work_root(self, session) -> str:
        """Override work_root method from IWorkfileHost.
        Modify workdir per host.

        Args:
            session (dict): Session context data.

        Returns:
            str: Path to new workdir.
        """
        return work_root(session)

    def get_context_data(self) -> dict:
        """Override abstract method from IPublishHost.
        Get global data related to creation-publishing from workfile.

        Returns:
            dict: Context data stored using 'update_context_data'.
        """
        property = bpy.context.scene.get(AYON_PROPERTY)
        if property:
            return property.to_dict()
        return {}

    def update_context_data(self, data: dict, changes: dict):
        """Override abstract method from IPublishHost.
        Store global context data to workfile.

        Args:
            data (dict): New data as are.
            changes (dict): Only data that has been changed. Each value has
                tuple with '(<old>, <new>)' value.
        """
        bpy.context.scene[AYON_PROPERTY] = data


def pype_excepthook_handler(*args):
    traceback.print_exception(*args)


def install():
    """Install Blender configuration for AYON."""
    sys.excepthook = pype_excepthook_handler

    pyblish.api.register_host("blender")
    pyblish.api.register_plugin_path(str(PUBLISH_PATH))

    register_loader_plugin_path(str(LOAD_PATH))
    register_creator_plugin_path(str(CREATE_PATH))

    lib.append_user_scripts()
    lib.set_app_templates_path()

    register_event_callback("new", on_new)
    register_event_callback("open", on_open)
    register_event_callback("before.save", on_before_save)

    _register_callbacks()

    if not IS_HEADLESS:
        ops.register()


def uninstall():
    """Uninstall Blender configuration for AYON."""
    sys.excepthook = ORIGINAL_EXCEPTHOOK

    pyblish.api.deregister_host("blender")
    pyblish.api.deregister_plugin_path(str(PUBLISH_PATH))

    deregister_loader_plugin_path(str(LOAD_PATH))
    deregister_creator_plugin_path(str(CREATE_PATH))

    if not IS_HEADLESS:
        ops.unregister()


def show_message(title, message):
    from ayon_core.tools.utils import show_message_dialog
    from .ops import BlenderApplication

    BlenderApplication.get_app()

    show_message_dialog(
        title=title,
        message=message,
        level="warning")


def message_window(title, message):
    from .ops import (
        MainThreadItem,
        execute_in_main_thread,
        _process_app_events
    )

    mti = MainThreadItem(show_message, title, message)
    execute_in_main_thread(mti)
    _process_app_events()


def get_frame_range(task_entity=None) -> Union[Dict[str, int], None]:
    """Get the task entity's frame range and handles

    Args:
        task_entity (Optional[dict]): Task Entity.
            When not provided defaults to current context task.

    Returns:
        Union[Dict[str, int], None]: Dictionary with
            frame start, frame end, handle start, handle end.
    """
    # Set frame start/end
    if task_entity is None:
        task_entity = get_current_task_entity(fields={"attrib"})
    task_attributes = task_entity["attrib"]
    frame_start = int(task_attributes["frameStart"])
    frame_end = int(task_attributes["frameEnd"])
    handle_start = int(task_attributes["handleStart"])
    handle_end = int(task_attributes["handleEnd"])
    frame_start_handle = frame_start - handle_start
    frame_end_handle = frame_end + handle_end

    return {
        "frameStart": frame_start,
        "frameEnd": frame_end,
        "handleStart": handle_start,
        "handleEnd": handle_end,
        "frameStartHandle": frame_start_handle,
        "frameEndHandle": frame_end_handle,
    }


def set_frame_range(entity: dict):
    scene = bpy.context.scene

    # Default scene settings
    frame_start = scene.frame_start
    frame_end = scene.frame_end
    fps = scene.render.fps / scene.render.fps_base

    if not entity:
        return

    attrib = entity["attrib"]
    if attrib.get("frameStart"):
        frame_start = attrib.get("frameStart")
    if attrib.get("frameEnd"):
        frame_end = attrib.get("frameEnd")
    if attrib.get("fps"):
        fps = attrib.get("fps")

    # Should handles be included, defined by settings
    settings = get_project_settings(get_current_project_name())
    task_type = entity.get("taskType")
    include_handles_settings = settings["blender"]["include_handles"]
    include_handles = include_handles_settings["include_handles_default"]
    profile = filter_profiles(
        include_handles_settings["profiles"],
        key_values={
            "task_types": task_type,
            "task_names": entity["name"]
        }
    )
    if profile:
        include_handles = profile["include_handles"]
    if include_handles:
        frame_start -= int(attrib.get("handleStart", 0))
        frame_end += int(attrib.get("handleEnd", 0))

    scene.frame_start = frame_start
    scene.frame_end = frame_end
    scene.render.fps = round(fps)
    scene.render.fps_base = round(fps) / fps


def set_resolution(entity: dict):
    scene = bpy.context.scene

    # Default scene settings
    resolution_x = scene.render.resolution_x
    resolution_y = scene.render.resolution_y

    if not entity:
        return

    attrib = entity["attrib"]
    if attrib.get("resolutionWidth"):
        resolution_x = attrib.get("resolutionWidth")
    if attrib.get("resolutionHeight"):
        resolution_y = attrib.get("resolutionHeight")

    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y


def set_unit_scale_from_settings(unit_scale_settings=None):
    if unit_scale_settings is None:
        return
    unit_scale_enabled = unit_scale_settings.get("enabled")
    if unit_scale_enabled:
        unit_scale = unit_scale_settings["base_file_unit_scale"]
        bpy.context.scene.unit_settings.scale_length = unit_scale


def on_new():
    project = get_current_project_name()
    settings = get_project_settings(project).get("blender")

    set_resolution_startup = settings.get("set_resolution_startup")
    set_frames_startup = settings.get("set_frames_startup")

    task_entity = get_current_task_entity()

    if set_resolution_startup:
        set_resolution(task_entity)
    if set_frames_startup:
        set_frame_range(task_entity)

    unit_scale_settings = settings.get("unit_scale_settings")
    set_unit_scale_from_settings(unit_scale_settings=unit_scale_settings)


def on_open():
    project = os.environ.get("AYON_PROJECT_NAME")
    settings = get_project_settings(project).get("blender")

    set_resolution_startup = settings.get("set_resolution_startup")
    set_frames_startup = settings.get("set_frames_startup")

    task_entity = get_current_task_entity()

    if set_resolution_startup:
        set_resolution(task_entity)
    if set_frames_startup:
        set_frame_range(task_entity)

    unit_scale_settings = settings.get("unit_scale_settings")
    unit_scale_enabled = unit_scale_settings.get("enabled")
    apply_on_opening = unit_scale_settings.get("apply_on_opening")
    if unit_scale_enabled and apply_on_opening:
        unit_scale = unit_scale_settings.get("base_file_unit_scale")
        prev_unit_scale = bpy.context.scene.unit_settings.scale_length

        if unit_scale != prev_unit_scale:
            bpy.context.scene.unit_settings.scale_length = unit_scale

            message_window(
                "Base file unit scale changed",
                "Base file unit scale changed to match the project settings.")


def on_before_save(event):
    """Handle the event before saving a Blender file.

    When saving to a new scene name, e.g. on incrementing the workfile then
    update the render paths to match the new scene name by replacing the old
    scene name with the new one in all render paths.
    """
    blend_path_before: str = bpy.data.filepath
    blend_path_after: str = event.get("filename")

    if not blend_path_before:
        # Saving from a new unsaved file, no need to check for changes.
        return

    blend_name_before: str = os.path.splitext(
        os.path.basename(blend_path_before))[0]
    blend_name_after: str = os.path.splitext(
        os.path.basename(blend_path_after))[0]
    if blend_name_before != blend_name_after:
        print(f"Detected scene name change from {blend_name_before} to "
              f"{blend_name_after}")
        # TODO: We may want to allow disabling this feature, especially after
        #  Blender 4.5+ supporting the `{blend_name}` in templates in render
        #  paths to avoid needing to hardcode the blender scene filename into
        #  those paths.
        # Update any render paths if they previously contained the scene name
        # Warning: if the scene name is `a` before and now `helloworld` then
        #  this may easily get out of hand by turning `asset` into
        #  `helloworldsset`, but since filenames tend to be longer and
        #  contain version numbers, this is not expected to happen often.
        search_replace_render_paths(blend_name_before, blend_name_after)


@bpy.app.handlers.persistent
def _on_save_pre(filename: str):
    emit_event("before.save", data={"filename": filename})


@bpy.app.handlers.persistent
def _on_save_post(*args):
    emit_event("save")


@bpy.app.handlers.persistent
def _on_load_post(*args):
    # Detect new file or opening an existing file
    if bpy.data.filepath:
        # Likely this was an open operation since it has a filepath
        emit_event("open")
    else:
        emit_event("new")

    ops.OpenFileCacher.post_load()


def _register_callbacks():
    """Register callbacks for certain events."""
    def _remove_handler(handlers: List, callback: Callable):
        """Remove the callback from the given handler list."""

        try:
            handlers.remove(callback)
        except ValueError:
            pass

    # TODO (jasper): implement on_init callback?

    # Be sure to remove existig ones first.
    _remove_handler(bpy.app.handlers.save_pre, _on_save_pre)
    _remove_handler(bpy.app.handlers.save_post, _on_save_post)
    _remove_handler(bpy.app.handlers.load_post, _on_load_post)

    bpy.app.handlers.save_pre.append(_on_save_pre)
    bpy.app.handlers.save_post.append(_on_save_post)
    bpy.app.handlers.load_post.append(_on_load_post)

    log.info("Installed event handler _on_save_pre...")
    log.info("Installed event handler _on_save_post...")
    log.info("Installed event handler _on_load_post...")


def _discover_gui() -> Optional[Callable]:
    """Return the most desirable of the currently registered GUIs"""

    # Prefer last registered
    guis = reversed(pyblish.api.registered_guis())

    for gui in guis:
        try:
            gui = __import__(gui).show
        except (ImportError, AttributeError):
            continue
        else:
            return gui

    return None


def get_ayon_property(node):
    property = node.get(AYON_PROPERTY)
    if not property:
        # Backwards compatibility: Update legacy
        # avalon property if found on the node
        property = node.get(AVALON_PROPERTY)
        if property:
            log.debug(
                f"Replacing {node.name}'s Avalon "
                f"property to {node.name}'s Ayon property"
            )
            node[AYON_PROPERTY] = property
            del node[AVALON_PROPERTY]
    return property


def convert_avalon_instances():
    avalon_instances = bpy.data.collections.get(AVALON_INSTANCES)
    if not avalon_instances:
        return
    ayon_instances = bpy.data.collections.get(AYON_INSTANCES)
    if ayon_instances:
        avalon_instance_objs = (
            avalon_instances.objects if avalon_instances else []
        )
        # link the objects parented from
        # avalon instance to ayon instance
        for instance_obj in avalon_instance_objs:
            ayon_instances.children.link(instance_obj)

        for children in avalon_instances.children_recursive:
            if isinstance(children, bpy.types.Collection):
                bpy.data.collections.remove(children)
            else:
                bpy.data.objects.remove(children)

        # remove deprecated avalon references
        bpy.data.collections.remove(avalon_instances)
    else:
        avalon_instances.name = AYON_INSTANCES


def add_to_ayon_container(
    container: Union[bpy.types.Collection, bpy.types.Object]
):
    """Add the container (object or collection) to the AYON container."""
    ayon_container = get_ayon_container()
    if isinstance(container, bpy.types.Collection):
        ayon_container.children.link(container)
    elif isinstance(container, bpy.types.Object):
        ayon_container.objects.link(container)


def get_ayon_container() -> bpy.types.Collection:
    """Get Ayon Container

    Returns:
         bpy.types.Collection: Ayon containers collection
    """
    ayon_container = bpy.data.collections.get(AYON_CONTAINERS)
    if ayon_container:
        return ayon_container

    # Backwards compatibility, check for legacy Avalon container
    avalon_container = bpy.data.collections.get(AVALON_CONTAINERS)
    if avalon_container:
        # Convert legacy Avalon container to Ayon container
        log.debug(
            "Converting legacy Avalon container to AYON container."
        )
        # Rename the collection
        avalon_container.name = AYON_CONTAINERS
        return avalon_container

    # Create a new AYON container if it does not exist
    return ensure_ayon_container()


def ensure_ayon_container() -> bpy.types.Collection:
    """Ensure AYON_CONTAINERS exists and is ready for use."""
    ayon_container = bpy.data.collections.get(AYON_CONTAINERS)
    if ayon_container:
        return ayon_container

    # Create and configure container
    ayon_container = bpy.data.collections.new(name=AYON_CONTAINERS)
    bpy.context.scene.collection.children.link(ayon_container)
    ayon_container.color_tag = "COLOR_02"
    ayon_container.use_fake_user = True
    return ayon_container


def metadata_update(node: bpy.types.bpy_struct_meta_idprop, data: Dict):
    """Imprint the node with metadata.

    Existing metadata will be updated.
    """

    if not node.get(AYON_PROPERTY):
        node[AYON_PROPERTY] = dict()
    for key, value in data.items():
        if value is None:
            continue
        node[AYON_PROPERTY][key] = value


def get_container_name(name: str,
                       namespace: str,
                       context: Dict,
                       suffix: str):
    """Function to get container name

    Args:
        name: Name of resulting assembly
        namespace: Namespace under which to host container
        context: Asset information
        suffix: Suffix of container

    Returns:
        The name of the container assembly
    """
    node_name = f"{context['folder']['name']}_{name}"
    if namespace:
        node_name = f"{namespace}:{node_name}"
    if suffix:
        node_name = f"{node_name}_{suffix}"

    return node_name



def containerise(name: str,
                 namespace: str,
                 nodes: List,
                 context: Dict,
                 loader: Optional[str] = None,
                 suffix: Optional[str] = "CON") -> bpy.types.Collection:
    """Bundle `nodes` into an assembly and imprint it with metadata

    Containerisation enables a tracking of version, author and origin
    for loaded assets.

    Arguments:
        name: Name of resulting assembly
        namespace: Namespace under which to host container
        nodes: Long names of nodes to containerise
        context: Asset information
        loader: Name of loader used to produce this container.
        suffix: Suffix of container, defaults to `_CON`.

    Returns:
        The container assembly

    """

    node_name = get_container_name(name, namespace, context, suffix)
    container = bpy.data.collections.new(name=node_name)
    # Link the children nodes
    for obj in nodes:
        if isinstance(obj, bpy.types.Object):
            container.objects.link(obj)
        elif isinstance(obj, bpy.types.Collection):
            container.children.link(obj)
        else:
            raise TypeError(f"Unsupported type {type(obj)} in nodes list.")

    data = {
        "schema": "ayon:container-3.0",
        "id": AYON_CONTAINER_ID,
        "name": name,
        "namespace": namespace or '',
        "loader": str(loader),
        "representation": context["representation"]["id"],
        "project_name": context["project"]["name"],
    }

    metadata_update(container, data)
    add_to_ayon_container(container)

    return container


def containerise_existing(
        container: bpy.types.Collection,
        name: str,
        namespace: str,
        context: Dict,
        loader: Optional[str] = None,
        suffix: Optional[str] = "CON") -> bpy.types.Collection:
    """Imprint or update container with metadata.

    Arguments:
        name: Name of resulting assembly
        namespace: Namespace under which to host container
        context: Asset information
        loader: Name of loader used to produce this container.
        suffix: Suffix of container, defaults to `_CON`.

    Returns:
        The container assembly
    """

    node_name = container.name
    if suffix:
        node_name = f"{node_name}_{suffix}"
    container.name = node_name
    data = {
        "schema": "ayon:container-3.0",
        "id": AYON_CONTAINER_ID,
        "name": name,
        "namespace": namespace or '',
        "loader": str(loader),
        "representation": context["representation"]["id"],
        "project_name": context["project"]["name"],
    }

    metadata_update(container, data)
    add_to_ayon_container(container)

    return container


def parse_container(container: bpy.types.Collection,
                    validate: bool = True) -> Dict:
    """Return the container node's full container data.

    Args:
        container: A container node name.
        validate: turn the validation for the container on or off

    Returns:
        The container schema data for this container node.

    """

    data = lib.read(container)

    # Append transient data
    data["objectName"] = container.name
    data["node"] = container  # store parsed object for easy access in loader

    if validate:
        schema.validate(data)

    return data


def ls() -> Iterator:
    """List containers from active Blender scene.

    This is the host-equivalent of api.ls(), but instead of listing assets on
    disk, it lists assets already loaded in Blender; once loaded they are
    called containers.
    """
    container_ids = {
        AYON_CONTAINER_ID,
        # Backwards compatibility
        AVALON_CONTAINER_ID
    }

    for id_type in container_ids:
        for container in lib.lsattr("id", id_type):
            yield parse_container(container)

    # Compositor nodes are not in `bpy.data` that `lib.lsattr` looks in.
    node_tree = bpy.context.scene.node_tree
    if node_tree:
        for node in node_tree.nodes:
            ayon_prop = node.get(AYON_PROPERTY)
            if not ayon_prop:
                avalon_prop = node.get(AVALON_PROPERTY)
                if not avalon_prop:
                    continue
                else:
                    node[AYON_PROPERTY] = avalon_prop
                    ayon_prop = avalon_prop
                    del node[AVALON_PROPERTY]

            if ayon_prop.get("id") not in container_ids:
                continue

            yield parse_container(node)

    # Shader nodes are not available in a way that `lib.lsattr` can find.
    for material in bpy.data.materials:
        material_node_tree = material.node_tree
        if not material_node_tree:
            continue

        for shader_node in material_node_tree.nodes:
            ayon_shader_node = get_ayon_property(shader_node)
            if not ayon_shader_node:
                continue

            if ayon_shader_node.get("id") not in container_ids:
                continue

            yield parse_container(shader_node)


def publish():
    """Shorthand to publish from within host."""

    return pyblish.util.publish()
