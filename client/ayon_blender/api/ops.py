"""Blender operators and menus for use with AYON."""
from __future__ import annotations

import os
import sys
import platform
import time
import traceback
import collections
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional

from qtpy import QtWidgets, QtCore

import bpy
import bpy.utils.previews

from ayon_core.lib import get_ayon_launcher_args
from ayon_core.settings import get_project_settings
from ayon_core.pipeline import (
    get_current_folder_path,
    get_current_task_name,
    get_current_project_name
)
from ayon_core.pipeline.context_tools import (
    get_current_task_entity,
    version_up_current_workfile
)
from ayon_core.style import load_stylesheet

from ayon_blender.ipc_communication import IPCServer

from .tools import BlenderWorkfilesController, get_ui_process_script_path
from . import pipeline
from . import render_lib

logger = logging.getLogger(__name__)

PREVIEW_COLLECTIONS: Dict = dict()
TIMER_INTERVAL: float = 0.01


# IPC and external UI process management
class _IPCConnection:
    server: IPCServer | None = None
    ui_process: subprocess.Popen | None = None
    workfiles_controller: BlenderWorkfilesController = (
        BlenderWorkfilesController()
    )


def _external_ui_launcher(ipc_host: str, ipc_port: int, session_token: str) -> subprocess.Popen:
    launcher_script = get_ui_process_script_path()
    env = os.environ.copy()
    env["AYON_IPC_PID"] = str(os.getpid())
    env["AYON_IPC_HOST"] = ipc_host
    env["AYON_IPC_PORT"] = str(ipc_port)
    env["AYON_IPC_TOKEN"] = session_token
    # USED to debug the external UI host process.
    launch_args = get_ayon_launcher_args("run", str(launcher_script))
    print("Launching external UI host with: %s", launch_args)
    logger.info("Launching external UI host with: %s", launch_args)
    return subprocess.Popen(
        launch_args,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _is_ipc_server_healthy() -> bool:
    """Return whether IPC server instance is alive and listening."""
    server = _IPCConnection.server
    if server is None:
        return False

    thread = server.server_thread
    if not server.running or thread is None or not thread.is_alive():
        return False

    return server.server_socket is not None


def execute_function_in_main_thread(f):
    """Decorator to move a function call into main thread items"""
    def wrapper(*args, **kwargs):
        mti = MainThreadItem(f, *args, **kwargs)
        execute_in_main_thread(mti)
    return wrapper


class BlenderApplication:
    _instance = None
    blender_windows = {}

    @classmethod
    def get_app(cls):
        print("Can't use Qt window anymore")
        return None

    @classmethod
    def store_window(cls, identifier, window):
        print(f"Can't store window anymore '{identifier}'")

    @classmethod
    def get_window(cls, identifier):
        print("Can't store window anymore")
        return cls.blender_windows.get(identifier)


class MainThreadItem:
    """Structure to store information about callback in main thread.

    Item should be used to execute callback in main thread which may be needed
    for execution of Qt objects.

    Item store callback (callable variable), arguments and keyword arguments
    for the callback. Item hold information about it's process.
    """
    not_set = object()
    sleep_time = 0.1

    def __init__(self, callback, *args, **kwargs):
        self.done = False
        self.exception = self.not_set
        self.result = self.not_set
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def execute(self):
        """Execute callback and store its result.

        Method must be called from main thread. Item is marked as `done`
        when callback execution finished. Store output of callback of exception
        information when callback raises one.
        """
        print("Executing process in main thread")
        if self.done:
            print("- item is already processed")
            return

        callback = self.callback
        args = self.args
        kwargs = self.kwargs
        print("Running callback: {}".format(str(callback)))
        try:
            result = callback(*args, **kwargs)
            self.result = result

        except Exception:
            self.exception = sys.exc_info()

        finally:
            print("Done")
            self.done = True

    def wait(self):
        """Wait for result from main thread.

        This method stops current thread until callback is executed.

        Returns:
            object: Output of callback. May be any type or object.

        Raises:
            Exception: Reraise any exception that happened during callback
                execution.
        """
        while not self.done:
            print(self.done)
            time.sleep(self.sleep_time)

        if self.exception is self.not_set:
            return self.result
        raise self.exception


class GlobalClass:
    main_thread_callbacks = collections.deque()


def execute_in_main_thread(main_thead_item):
    GlobalClass.main_thread_callbacks.append(main_thead_item)


def _init_ipc_server():
    """Initialize the IPC server for external UI communication."""
    if _is_ipc_server_healthy():
        return _IPCConnection.server

    # Recover from stale server objects that are no longer listening.
    if _IPCConnection.server is not None:
        logger.warning("IPC server was stale; recreating it")
        try:
            _IPCConnection.server.stop()
        except Exception:
            logger.debug("Failed stopping stale IPC server", exc_info=True)
        _IPCConnection.server = None

    try:
        server = IPCServer()
        port = server.start()
        logger.info("IPC server listening on 127.0.0.1:%s", port)

        # Register handlers for common operations
        _register_ipc_handlers(server)
        _IPCConnection.server = server

        _ensure_external_ui_process()

        return _IPCConnection.server

    except Exception as e:
        logger.error(f"Failed to initialize IPC server: {e}", exc_info=True)
        _IPCConnection.server = None
        return None


def _ensure_external_ui_process():
    """Ensure external UI process is running when external UI mode is enabled."""
    if not _is_ipc_server_healthy():
        _init_ipc_server()

    if _IPCConnection.server is None:
        return

    if _IPCConnection.ui_process and _IPCConnection.ui_process.poll() is None:
        return

    token = _IPCConnection.server.get_session_token()
    _IPCConnection.ui_process = _external_ui_launcher(
        ipc_host="127.0.0.1",
        ipc_port=_IPCConnection.server.port,
        session_token=token,
    )
    logger.info(
        "External UI process launched (PID: %s)",
        _IPCConnection.ui_process.pid
    )
    # TODO better way to wait for the external UI process
    # - maybe store requests to send if client is not connected?
    for _ in range(300):
        if _IPCConnection.server.clients:
            break
        time.sleep(0.1)


def _register_ipc_handlers(server: IPCServer):
    """Register request handlers for IPC server."""

    _IPCConnection.workfiles_controller.register_ipc_handler(server)


def _shutdown_ipc_server():
    """Shutdown the IPC server and external UI process."""
    global _loader_backend_bridge

    if _IPCConnection.ui_process:
        try:
            _IPCConnection.ui_process.terminate()
            _IPCConnection.ui_process.wait(timeout=5)
        except Exception as e:
            logger.warning(f"Error terminating UI process: {e}")
        _IPCConnection.ui_process = None

    if _IPCConnection.server:
        try:
            _IPCConnection.server.stop()
        except Exception as e:
            logger.error(f"Error stopping IPC server: {e}")
        _IPCConnection.server = None

    _loader_backend_bridge = None


def _process_app_events() -> Optional[float]:
    """Process the events of the Qt app if the window is still visible.

    If the app has any top level windows and at least one of them is visible
    return the time after which this function should be run again. Else return
    None, so the function is not run again and will be unregistered.
    """
    # Process main thread callbacks
    while GlobalClass.main_thread_callbacks:
        main_thread_item = GlobalClass.main_thread_callbacks.popleft()
        main_thread_item.execute()
        if main_thread_item.exception is not MainThreadItem.not_set:
            _clc, val, tb = main_thread_item.exception
            msg = str(val)
            detail = "\n".join(traceback.format_exception(_clc, val, tb))
            dialog = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Warning,
                "Error",
                msg)
            dialog.setMinimumWidth(500)
            dialog.setDetailedText(detail)
            dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            dialog.setStyleSheet(load_stylesheet())
            # Ensure the dialog stays on top and is properly focused
            dialog.setWindowFlags(
                dialog.windowFlags() |
                QtCore.Qt.WindowStaysOnTopHint |
                QtCore.Qt.Dialog
            )
            dialog.raise_()
            dialog.activateWindow()
            dialog.open()

    # Process IPC requests (send pending events to clients)
    if _IPCConnection.server:
        _IPCConnection.server.process_requests()

    return TIMER_INTERVAL


class LaunchToolOperator(bpy.types.Operator):
    """A Base class for operators to launch a Qt app."""

    _tool_name: str = None
    _params: dict | None = None
    bl_idname: str = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.bl_idname is None:
            raise NotImplementedError("Attribute `bl_idname` must be set!")
        print(f"Initialising {self.bl_idname}...")

        _init_ipc_server()

        if not bpy.app.timers.is_registered(_process_app_events):
            bpy.app.timers.register(
                _process_app_events,
                persistent=True
            )

    def execute(self, context):
        """Execute using external UI process via IPC."""
        _ensure_external_ui_process()
        server = _IPCConnection.server
        if not server:
            return {"CANCELLED"}

        try:
            if not self._tool_name:
                print("No tool name specified for external UI launch")
                return {"CANCELLED"}

            server.trigger_method(
                self._tool_name,
                "show",
                self._params,
            )
            return {"FINISHED"}

        except Exception as e:
            logger.error(f"Error launching external UI: {e}", exc_info=True)
            return {"CANCELLED"}

    def before_window_show(self):
        return


class LaunchCreator(LaunchToolOperator):
    """Launch AYON Creator."""

    bl_idname = "wm.ayon_creator"
    bl_label = "Create..."
    _tool_name = "publisher"
    _params = {"tab": "create"}

    def execute(self, context):
        return super().execute(context)


class LaunchLoader(LaunchToolOperator):
    """Launch AYON Loader."""

    bl_idname = "wm.ayon_loader"
    bl_label = "Load..."
    _tool_name = "loader"


class LaunchPublisher(LaunchToolOperator):
    """Launch AYON Publisher."""

    bl_idname = "wm.ayon_publisher"
    bl_label = "Publish..."
    _tool_name = "publisher"
    _params = {"tab": "publish"}

    def execute(self, context):
        return super().execute(context)


class LaunchManager(LaunchToolOperator):
    """Launch AYON Manager."""

    bl_idname = "wm.ayon_manager"
    bl_label = "Manage..."
    _tool_name = "sceneinventory"


class LaunchLibrary(LaunchToolOperator):
    """Launch Library Loader."""

    bl_idname = "wm.library_loader"
    bl_label = "Library..."
    _tool_name = "libraryloader"


class LaunchWorkFiles(LaunchToolOperator):
    """Launch AYON Work Files."""

    bl_idname = "wm.ayon_workfiles"
    bl_label = "Work Files..."
    _tool_name = "workfiles"

    def execute(self, context):
        return super().execute(context)


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
    def execute(self, context):
        from .workfile_template_builder import open_template
        open_template()
        return {"FINISHED"}


class CreatePlaceholder(LaunchToolOperator):
    """Create Placeholder from ayon template settings."""

    bl_idname = "wm.ayon_create_placeholder"
    bl_label = "Create Placeholder"
    def execute(self, context):
        from .workfile_template_builder import create_placeholder
        window = create_placeholder()
        BlenderApplication.store_window(self.bl_idname, window)
        self._window = window
        return super().execute(context)


class UpdatePlaceholder(LaunchToolOperator):
    """Update Placeholder from ayon template settings."""

    bl_idname = "wm.ayon_update_placeholder"
    bl_label = "Update Placeholder"
    def execute(self, context):
        from .workfile_template_builder import update_placeholder
        window = update_placeholder()
        BlenderApplication.store_window(self.bl_idname, window)
        self._window = window
        return super().execute(context)


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


# def _on_render_init(scene):
#     """Handle render initialization."""
#     if _IPCConnection.server:
#         _IPCConnection.server.publish_event("render_started", {
#             "scene": scene.name if scene else ""
#         })
#     logger.debug("Render started")
#
#
# def _on_render_complete(scene):
#     """Handle render completion."""
#     if _IPCConnection.server:
#         _IPCConnection.server.publish_event("render_finished", {
#             "scene": scene.name if scene else ""
#         })
#     logger.debug("Render completed")
#
#
# def _on_render_cancel(scene):
#     """Handle render cancellation."""
#     if _IPCConnection.server:
#         _IPCConnection.server.publish_event("render_cancelled", {
#             "scene": scene.name if scene else ""
#         })
#     logger.debug("Render cancelled")


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
    #
    # # Register render handlers for Blender busy state detection
    # bpy.app.handlers.render_init.append(_on_render_init)
    # bpy.app.handlers.render_complete.append(_on_render_complete)
    # bpy.app.handlers.render_cancel.append(_on_render_cancel)


def unregister():
    """Unregister the operators and menu."""

    # Unregister render handlers
    # try:
    #     bpy.app.handlers.render_init.remove(_on_render_init)
    #     bpy.app.handlers.render_complete.remove(_on_render_complete)
    #     bpy.app.handlers.render_cancel.remove(_on_render_cancel)
    # except (ValueError, AttributeError):
    #     pass

    # Shutdown IPC server
    _shutdown_ipc_server()

    pcoll = PREVIEW_COLLECTIONS.pop("ayon")
    bpy.utils.previews.remove(pcoll)
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_ayon_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
