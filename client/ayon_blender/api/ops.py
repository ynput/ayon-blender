"""Blender operators and menus for use with AYON."""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Dict

import bpy
import bpy.utils.previews

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import (
    get_current_folder_path,
    get_current_task_name,
    get_current_project_name,
)
from ayon_core.pipeline.context_tools import (
    get_current_task_entity,
    version_up_current_workfile
)
from ayon_core.tools.ipc_utils import IPCHostTools

from .execution import process_main_thread_callbacks
from . import pipeline
from . import render_lib

logger = logging.getLogger(__name__)

PREVIEW_COLLECTIONS: Dict = dict()
TIMER_INTERVAL: float = 0.01


def _process_app_events() -> float:
    """Process the events of the Qt app if the window is still visible.

    If the app has any top level windows and at least one of them is visible
    return the time after which this function should be run again. Else return
    None, so the function is not run again and will be unregistered.
    """
    # Process main thread callbacks
    process_main_thread_callbacks()

    # Process IPC requests (send pending events to clients)
    IPCHostTools.process_requests()

    return TIMER_INTERVAL


class BlenderApplication:
    @classmethod
    def store_window(cls, identifier, window):
        # TODO remove
        print(f"Can't store window anymore '{identifier}'")


class LaunchToolOperator(bpy.types.Operator):
    """A Base class for operators to launch a Qt app."""

    bl_idname: str = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.bl_idname is None:
            raise NotImplementedError("Attribute `bl_idname` must be set!")
        print(f"Initialising {self.bl_idname}...")

        if not bpy.app.timers.is_registered(_process_app_events):
            bpy.app.timers.register(
                _process_app_events,
                persistent=True
            )

    def execute(self, context):
        """Execute using external UI process via IPC."""
        raise ValueError(
            f"Tool '{self.__class__.__name__}' is not implemented "
        )

class LaunchCreator(LaunchToolOperator):
    """Launch AYON Creator."""

    bl_idname = "wm.ayon_creator"
    bl_label = "Create..."

    def execute(self, context):
        IPCHostTools.show_publisher(tab="create")
        return {"FINISHED"}


class LaunchLoader(LaunchToolOperator):
    """Launch AYON Loader."""

    bl_idname = "wm.ayon_loader"
    bl_label = "Load..."

    def execute(self, context):
        IPCHostTools.show_loader()
        return {"FINISHED"}


class LaunchPublisher(LaunchToolOperator):
    """Launch AYON Publisher."""

    bl_idname = "wm.ayon_publisher"
    bl_label = "Publish..."

    def execute(self, context):
        IPCHostTools.show_publisher()
        return {"FINISHED"}


class LaunchManager(LaunchToolOperator):
    """Launch AYON Manager."""

    bl_idname = "wm.ayon_manager"
    bl_label = "Manage..."


class LaunchLibrary(LaunchToolOperator):
    """Launch Library Loader."""

    bl_idname = "wm.library_loader"
    bl_label = "Library..."

    def execute(self, context):
        IPCHostTools.show_loader()
        return {"FINISHED"}


class LaunchWorkFiles(LaunchToolOperator):
    """Launch AYON Work Files."""

    bl_idname = "wm.ayon_workfiles"
    bl_label = "Work Files..."

    def execute(self, context):
        IPCHostTools.show_workfiles()
        return {"FINISHED"}


class SetFrameRange(bpy.types.Operator):
    bl_idname = "wm.ayon_set_frame_range"
    bl_label = "Set Frame Range"

    def execute(self, context):
        task_entity = get_current_task_entity()
        pipeline.set_frame_range(task_entity)
        return {"FINISHED"}


class SetResolution(bpy.types.Operator):
    bl_idname = "wm.ayon_set_resolution"
    bl_label = "Set Resolution"

    def execute(self, context):
        task_entity = get_current_task_entity()
        pipeline.set_resolution(task_entity)
        return {"FINISHED"}


class SetUnitScale(bpy.types.Operator):
    bl_idname = "wm.ayon_set_unit_scale"
    bl_label = "Set Unit Scale"

    def execute(self, context):
        project = get_current_project_name()
        settings = get_project_settings(project).get("blender")
        pipeline.set_unit_scale_from_settings(blender_settings=settings)
        return {"FINISHED"}


class CreateRenderSetup(bpy.types.Operator):
    bl_idname = "wm.ayon_create_render_setup"
    bl_label = "Create Render Setup"
    bl_description = (
        "Create a render setup for the current scene in Compositor based on "
        "the current AYON project settings."
    )

    def execute(self, context):
        # TODO: Likely don't want to hardcode this to just `Main`?
        render_lib.prepare_rendering(variant_name="Main")
        return {"FINISHED"}


class VersionUpWorkfile(LaunchToolOperator):
    """Perform Incremental Save Workfile."""

    bl_idname = "wm.ayon_version_up_workfile"
    bl_label = "Version Up Workfile"

    def execute(self, context):
        version_up_current_workfile()
        return {"FINISHED"}


class CreateFirstWorkfileFromTemplate(LaunchToolOperator):
    """Build Workfile from ayon template settings."""

    bl_idname = "wm.ayon_create_first_workfile_from_template"
    bl_label = "Create First Workfile from Template"
    def execute(self, context):
        from .workfile_template_builder import create_first_workfile_from_template
        create_first_workfile_from_template()
        return {"FINISHED"}


class BuildWorkfileFromTemplate(LaunchToolOperator):
    """Build Workfile from ayon template settings."""

    bl_idname = "wm.ayon_build_workfile_from_template"
    bl_label = "Build Workfile from Template"
    def execute(self, context):
        from .workfile_template_builder import build_workfile_template
        build_workfile_template()
        return {"FINISHED"}


# TODO: implement update functionality when the load placeholder supported.
# class UpdateWorkfileFromTemplate(LaunchToolOperator):
#     """Update Workfile from ayon template settings."""

#     bl_idname = "wm.ayon_update_workfile_from_template"
#     bl_label = "Update Workfile from Template"
#     def execute(self, context):
#         from .workfile_template_builder import update_workfile_template
#         update_workfile_template()
#         return {"FINISHED"}


class OpenTemplate(LaunchToolOperator):
    """Open workfile template."""

    bl_idname = "wm.ayon_open_template"
    bl_label = "Open Template"
    # def execute(self, context):
    #     from .workfile_template_builder import open_template
    #     open_template()
    #     return {"FINISHED"}


class CreatePlaceholder(LaunchToolOperator):
    """Create Placeholder from ayon template settings."""

    bl_idname = "wm.ayon_create_placeholder"
    bl_label = "Create Placeholder"
    # def execute(self, context):
    #     from .workfile_template_builder import create_placeholder
    #     window = create_placeholder()
    #     BlenderApplication.store_window(self.bl_idname, window)
    #     self._window = window
    #     return super().execute(context)


class UpdatePlaceholder(LaunchToolOperator):
    """Update Placeholder from ayon template settings."""

    bl_idname = "wm.ayon_update_placeholder"
    bl_label = "Update Placeholder"
    # def execute(self, context):
    #     from .workfile_template_builder import update_placeholder
    #     window = update_placeholder()
    #     BlenderApplication.store_window(self.bl_idname, window)
    #     self._window = window
    #     return super().execute(context)


class TOPBAR_MT_ayon_Templated_Workfile(bpy.types.Menu):
    """AYON submenu example."""

    bl_idname = "TOPBAR_MT_AYON_TEMPLATED_WORKFILE"
    bl_label = "Templated Workfile"

    def draw(self, context):
        layout = self.layout
        layout.operator(
            CreateFirstWorkfileFromTemplate.bl_idname,
            text="Create First Workfile from Template"
        )
        layout.operator(
            BuildWorkfileFromTemplate.bl_idname,
            text="Build Workfile from Template"
        )
        # layout.operator(
        #     UpdateWorkfileFromTemplate.bl_idname,
        #     text="Update Workfile from Template"
        # )
        layout.separator()
        layout.operator(
            OpenTemplate.bl_idname,
            text="Open Template"
        )
        layout.operator(
            CreatePlaceholder.bl_idname,
            text="Create Placeholder"
        )
        layout.operator(
            UpdatePlaceholder.bl_idname,
            text="Update Placeholder"
        )


class TOPBAR_MT_ayon(bpy.types.Menu):
    """AYON menu."""

    bl_idname = "TOPBAR_MT_AYON"
    bl_label = os.environ.get("AYON_MENU_LABEL")

    def draw(self, context):
        """Draw the menu in the UI."""

        layout = self.layout

        pcoll = PREVIEW_COLLECTIONS.get("ayon")
        if pcoll:
            pyblish_menu_icon = pcoll["pyblish_menu_icon"]
            pyblish_menu_icon_id = pyblish_menu_icon.icon_id
        else:
            pyblish_menu_icon_id = 0

        folder_path = get_current_folder_path()
        task_name = get_current_task_name()
        context_label = f"{folder_path}, {task_name}"
        context_label_item = layout.row()
        context_label_item.operator(
            LaunchWorkFiles.bl_idname, text=context_label
        )
        context_label_item.enabled = False
        project_name = get_current_project_name()
        project_settings = get_project_settings(project_name)
        if project_settings["core"]["tools"]["ayon_menu"].get(
            "version_up_current_workfile"):
                layout.separator()
                layout.operator(
                    VersionUpWorkfile.bl_idname,
                    text="Version Up Workfile"
                )
                wm = bpy.context.window_manager
                keyconfigs = wm.keyconfigs
                keymap = keyconfigs.addon.keymaps.new(name='Window', space_type='EMPTY')
                keymap.keymap_items.new(
                    VersionUpWorkfile.bl_idname, 'S',
                    'PRESS', ctrl=True, alt=True
                )
                bpy.context.window_manager.keyconfigs.addon.keymaps.update()

        layout.separator()
        layout.operator(LaunchWorkFiles.bl_idname, text="Work Files...")

        layout.separator()
        layout.operator(LaunchCreator.bl_idname, text="Create...")
        layout.operator(LaunchLoader.bl_idname, text="Load...")
        layout.operator(
            LaunchPublisher.bl_idname,
            text="Publish...",
            icon_value=pyblish_menu_icon_id,
        )
        layout.operator(LaunchManager.bl_idname, text="Manage...")
        layout.operator(LaunchLibrary.bl_idname, text="Library...")
        layout.separator()
        layout.operator(SetFrameRange.bl_idname, text="Set Frame Range")
        layout.operator(SetResolution.bl_idname, text="Set Resolution")
        layout.operator(SetUnitScale.bl_idname, text="Set Unit Scale")
        layout.operator(CreateRenderSetup.bl_idname,
                        text="Create Render Setup")

        layout.separator()
        layout.menu(
            TOPBAR_MT_ayon_Templated_Workfile.bl_idname,
            text="Templated Workfile"
        )

def draw_ayon_menu(self, context):
    """Draw the AYON menu in the top bar."""

    self.layout.menu(TOPBAR_MT_ayon.bl_idname)


classes = [
    LaunchCreator,
    LaunchLoader,
    LaunchPublisher,
    LaunchManager,
    LaunchLibrary,
    LaunchWorkFiles,
    SetFrameRange,
    SetResolution,
    SetUnitScale,
    CreateRenderSetup,
    VersionUpWorkfile,
    CreateFirstWorkfileFromTemplate,
    BuildWorkfileFromTemplate,
    # UpdateWorkfileFromTemplate,
    OpenTemplate,
    CreatePlaceholder,
    UpdatePlaceholder,
    TOPBAR_MT_ayon_Templated_Workfile,
    TOPBAR_MT_ayon,
]


def register():
    "Register the operators and menu."

    pcoll = bpy.utils.previews.new()
    pyblish_icon_file = Path(__file__).parent / "icons" / "pyblish-32x32.png"
    pcoll.load("pyblish_menu_icon", str(pyblish_icon_file.absolute()), 'IMAGE')
    PREVIEW_COLLECTIONS["ayon"] = pcoll

    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_ayon_menu)


def unregister():
    """Unregister the operators and menu."""


    # Shutdown IPC server
    IPCHostTools.shutdown()

    pcoll = PREVIEW_COLLECTIONS.pop("ayon")
    bpy.utils.previews.remove(pcoll)
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_ayon_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
