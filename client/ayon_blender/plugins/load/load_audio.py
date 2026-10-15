"""Load audio in Blender."""

from pathlib import Path
from pprint import pformat
from typing import Dict, List, Optional

import bpy

from ayon_core.pipeline import AYON_CONTAINER_ID
from ayon_blender.api import plugin
from ayon_blender.api.constants import AYON_PROPERTY
from ayon_blender.api.pipeline import add_to_ayon_container


def get_all_strips(sequence_editor: bpy.types.SequenceEditor):
    """Return all strips of the sequence editor.

    Blender 4.4 renamed `sequences_all` to `strips_all` and Blender 5.0
    removed `sequences_all`.
    """
    if hasattr(sequence_editor, "strips_all"):
        return sequence_editor.strips_all
    return sequence_editor.sequences_all


def get_sequencer_scene() -> bpy.types.Scene:
    """Return the scene the sequencer operates on in the current context.

    Since Blender 5.0 the sequencer scene is defined per workspace instead
    of always being the active scene. It may be unset, in which case the
    sequencer operators can not run, so we then set it to the active scene.
    """
    context = bpy.context
    workspace = context.workspace
    if not hasattr(workspace, "sequencer_scene"):
        return context.scene
    if workspace.sequencer_scene is None:
        workspace.sequencer_scene = context.scene
    return workspace.sequencer_scene


def get_version_frame_start(context: dict) -> Optional[int]:
    """Return the start frame, including handles, of the version to load.

    Returns None if the version has no frame range data.
    """
    version_attrib = context["version"]["attrib"]
    frame_start = version_attrib.get("frameStart")
    if frame_start is None:
        return None
    handle_start = version_attrib.get("handleStart") or 0
    return int(frame_start - handle_start)


def add_sound_strip(scene: bpy.types.Scene, **kwargs):
    """Add a sound strip to the sequencer and return the created strip.

    The strip name is unique in the sequence editor so it may differ from
    the filename if a strip with that name already exists.
    """
    bpy.ops.sequencer.sound_strip_add(**kwargs)
    return scene.sequence_editor.active_strip


def remove_sound_strip(strip):
    """Remove a sound strip and its sound if it has no other users."""
    sound = strip.sound
    bpy.ops.sequencer.select_all(action='DESELECT')
    strip.select = True
    bpy.ops.sequencer.delete()
    if sound and not sound.users:
        bpy.data.sounds.remove(sound)


class AudioLoader(plugin.BlenderLoader):
    """Load audio in Blender."""

    product_base_types = {"audio"}
    product_types = product_base_types
    representations = {"*"}
    extensions = {"wav"}

    label = "Load Audio"
    icon = "volume-up"
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

        asset_name = plugin.prepare_scene_name(folder_name, product_name)
        unique_number = plugin.get_unique_number(folder_name, product_name)
        group_name = plugin.prepare_scene_name(
            folder_name, product_name, unique_number
        )
        namespace = namespace or f"{folder_name}_{unique_number}"

        asset_group = bpy.data.objects.new(group_name, object_data=None)
        add_to_ayon_container(asset_group)

        # Blender needs the Sequence Editor in the current window, to be able
        # to load the audio. We take one of the areas in the window, save its
        # type, and switch to the Sequence Editor. After loading the audio,
        # we switch back to the previous area.
        window_manager = bpy.context.window_manager
        old_type = window_manager.windows[-1].screen.areas[0].type
        window_manager.windows[-1].screen.areas[0].type = "SEQUENCE_EDITOR"

        # The sequencer scene must be resolved before copying the context,
        # otherwise the override would still contain an unset sequencer scene.
        scene = get_sequencer_scene()

        # Versions without frame range data start at the scene frame start
        frame_start = get_version_frame_start(context)
        if frame_start is None:
            frame_start = scene.frame_start

        # We override the context to load the audio in the sequence editor.
        oc = bpy.context.copy()
        oc["area"] = window_manager.windows[-1].screen.areas[0]

        with bpy.context.temp_override(**oc):
            strip = add_sound_strip(
                scene, filepath=libpath, frame_start=frame_start)
            audio = strip.name

        window_manager.windows[-1].screen.areas[0].type = old_type

        asset_group[AYON_PROPERTY] = {
            "schema": "ayon:container-3.0",
            "id": AYON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
            "libpath": libpath,
            "asset_name": asset_name,
            "objectName": group_name,
            "audio": audio,
            "project_name": context["project"]["name"],
        }

        objects = []
        self[:] = objects
        return [objects]

    def exec_update(self, container: Dict, context: Dict):
        """Update an audio strip in the sequence editor.

        Arguments:
            container (ayon:container-1.0): Container to update,
                from `host.ls()`.
            representation (ayon:representation-1.0): Representation to
                update, from `host.ls()`.
        """
        repre_entity = context["representation"]
        object_name = container["objectName"]
        asset_group = bpy.data.objects.get(object_name)
        libpath = Path(self.filepath_from_context(context))

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

        old_audio = container["audio"]

        # Blender needs the Sequence Editor in the current window, to be able
        # to update the audio. We take one of the areas in the window, save its
        # type, and switch to the Sequence Editor. After updating the audio,
        # we switch back to the previous area.
        window_manager = bpy.context.window_manager
        old_type = window_manager.windows[-1].screen.areas[0].type
        window_manager.windows[-1].screen.areas[0].type = "SEQUENCE_EDITOR"

        # The sequencer scene must be resolved before copying the context,
        # otherwise the override would still contain an unset sequencer scene.
        scene = get_sequencer_scene()

        # We override the context to load the audio in the sequence editor.
        oc = bpy.context.copy()
        oc["area"] = window_manager.windows[-1].screen.areas[0]

        with bpy.context.temp_override(**oc):
            old_strip = get_all_strips(scene.sequence_editor)[old_audio]

            # Keep the strip where the user placed it. Moving it to match
            # the new version is left to the user.
            channel = old_strip.channel
            frame_start = int(old_strip.frame_start)

            remove_sound_strip(old_strip)
            new_strip = add_sound_strip(
                scene,
                filepath=str(libpath),
                frame_start=frame_start,
                channel=channel,
            )
            new_audio = new_strip.name

        window_manager.windows[-1].screen.areas[0].type = old_type

        metadata["libpath"] = str(libpath)
        metadata["representation"] = repre_entity["id"]
        metadata["audio"] = new_audio
        metadata["project_name"] = context["project"]["name"]

    def exec_remove(self, container: Dict) -> bool:
        """Remove an audio strip from the sequence editor and the container.

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

        audio = container["audio"]

        # Blender needs the Sequence Editor in the current window, to be able
        # to remove the audio. We take one of the areas in the window, save its
        # type, and switch to the Sequence Editor. After removing the audio,
        # we switch back to the previous area.
        window_manager = bpy.context.window_manager
        old_type = window_manager.windows[-1].screen.areas[0].type
        window_manager.windows[-1].screen.areas[0].type = "SEQUENCE_EDITOR"

        # The sequencer scene must be resolved before copying the context,
        # otherwise the override would still contain an unset sequencer scene.
        scene = get_sequencer_scene()

        # We override the context to load the audio in the sequence editor.
        oc = bpy.context.copy()
        oc["area"] = window_manager.windows[-1].screen.areas[0]

        with bpy.context.temp_override(**oc):
            remove_sound_strip(get_all_strips(scene.sequence_editor)[audio])

        window_manager.windows[-1].screen.areas[0].type = old_type

        bpy.data.objects.remove(asset_group)

        return True
