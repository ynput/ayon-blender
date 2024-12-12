"""Blender operators and menus for use with Avalon."""

import os
import sys
import platform
import time
import traceback
import collections
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Union

from qtpy import QtWidgets, QtCore

import bpy
import bpy.utils.previews

from ayon_core import style
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
from ayon_core.tools.utils import host_tools

from .workio import OpenFileCacher
from . import pipeline

PREVIEW_COLLECTIONS: Dict = dict()

# This seems like a good value to keep the Qt app responsive and doesn't slow
# down Blender. At least on macOS I the interface of Blender gets very laggy if
# you make it smaller.
TIMER_INTERVAL: float = 0.01 if platform.system() == "Windows" else 0.1


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
        if cls._instance is None:
            # If any other addon or plug-in may have initialed a Qt application
            # before AYON then we should take the existing instance instead.
            application = QtWidgets.QApplication.instance()
            if application is None:
                application = QtWidgets.QApplication(sys.argv)

            # Ensure it is configured to our needs
            cls._prepare_qapplication(application)
            cls._instance = application

        return cls._instance

    @classmethod
    def _prepare_qapplication(cls, application: QtWidgets.QApplication):
        application.setQuitOnLastWindowClosed(False)
        application.setStyleSheet(style.load_stylesheet())
        application.lastWindowClosed.connect(cls.reset)

    @classmethod
    def reset(cls):
        cls._instance = None

    @classmethod
    def store_window(cls, identifier, window):
        current_window = cls.get_window(identifier)
        cls.blender_windows[identifier] = window
        if current_window:
            current_window.close()
            # current_window.deleteLater()

    @classmethod
    def get_window(cls, identifier):
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
    app = None
    main_thread_callbacks = collections.deque()
    is_windows = platform.system().lower() == "windows"


def execute_in_main_thread(main_thead_item):
    print("execute_in_main_thread")
    GlobalClass.main_thread_callbacks.append(main_thead_item)


def _process_app_events() -> Optional[float]:
    """Process the events of the Qt app if the window is still visible.

    If the app has any top level windows and at least one of them is visible
    return the time after which this function should be run again. Else return
    None, so the function is not run again and will be unregistered.
    """
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
            dialog.exec_()

        # Refresh Manager
        if GlobalClass.app:
            manager = BlenderApplication.get_window("WM_OT_avalon_manager")
            if manager:
                manager.refresh()

    if not GlobalClass.is_windows:
        if OpenFileCacher.opening_file:
            return TIMER_INTERVAL

        app = GlobalClass.app
        if app:
            app.processEvents()
            return TIMER_INTERVAL
    return TIMER_INTERVAL


class LaunchQtApp(bpy.types.Operator):
    """A Base class for operators to launch a Qt app."""

    _window = Union[QtWidgets.QDialog, ModuleType]
    _tool_name: str = None
    _init_args: Optional[List] = list()
    _init_kwargs: Optional[Dict] = dict()
    bl_idname: str = None

    def __init__(self):
        if self.bl_idname is None:
            raise NotImplementedError("Attribute `bl_idname` must be set!")
        print(f"Initialising {self.bl_idname}...")
        GlobalClass.app = BlenderApplication.get_app()

        if not bpy.app.timers.is_registered(_process_app_events):
            bpy.app.timers.register(
                _process_app_events,
                persistent=True
            )

    def execute(self, context):
        """Execute the operator.

        The child class must implement `execute()` where it only has to set
        `self._window` to the desired Qt window and then simply run
        `return super().execute(context)`.
        `self._window` is expected to have a `show` method.
        If the `show` method requires arguments, you can set `self._show_args`
        and `self._show_kwargs`. `args` should be a list, `kwargs` a
        dictionary.
        """

        if self._tool_name is None:
            if self._window is None:
                raise AttributeError("`self._window` is not set.")

        else:
            window = BlenderApplication.get_window(self.bl_idname)
            if window is None:
                window = host_tools.get_tool_by_name(self._tool_name)
                BlenderApplication.store_window(self.bl_idname, window)
            self._window = window

        if not isinstance(self._window, (QtWidgets.QWidget, ModuleType)):
            raise AttributeError(
                "`window` should be a `QWidget or module`. Got: {}".format(
                    str(type(self._window))
                )
            )

        self.before_window_show()

        def pull_to_front(window):
            """Pull window forward to screen.

            If Window is minimized this will un-minimize, then it can be raised
            and activated to the front.
            """
            window.setWindowState(
                (window.windowState() & ~QtCore.Qt.WindowMinimized) |
                QtCore.Qt.WindowActive
            )
            window.raise_()
            window.activateWindow()

        if isinstance(self._window, ModuleType):
            self._window.show()
            pull_to_front(self._window)

            # Pull window to the front
            window = None
            if hasattr(self._window, "window"):
                window = self._window.window
            elif hasattr(self._window, "_window"):
                window = self._window.window

            if window:
                BlenderApplication.store_window(self.bl_idname, window)

        else:
            origin_flags = self._window.windowFlags()
            on_top_flags = origin_flags | QtCore.Qt.WindowStaysOnTopHint
            self._window.setWindowFlags(on_top_flags)
            self._window.show()
            pull_to_front(self._window)

            # if on_top_flags != origin_flags:
            #     self._window.setWindowFlags(origin_flags)
            #     self._window.show()

        return {'FINISHED'}

    def before_window_show(self):
        return


class LaunchCreator(LaunchQtApp):
    """Launch Avalon Creator."""

    bl_idname = "wm.avalon_creator"
    bl_label = "Create..."
    _tool_name = "creator"

    def before_window_show(self):
        self._window.refresh()

    def execute(self, context):
        host_tools.show_publisher(tab="create")
        return {"FINISHED"}


class LaunchLoader(LaunchQtApp):
    """Launch AYON Loader."""

    bl_idname = "wm.avalon_loader"
    bl_label = "Load..."
    _tool_name = "loader"


class LaunchPublisher(LaunchQtApp):
    """Launch Avalon Publisher."""

    bl_idname = "wm.avalon_publisher"
    bl_label = "Publish..."

    def execute(self, context):
        host_tools.show_publisher(tab="publish")
        return {"FINISHED"}


class LaunchManager(LaunchQtApp):
    """Launch Avalon Manager."""

    bl_idname = "wm.avalon_manager"
    bl_label = "Manage..."
    _tool_name = "sceneinventory"


class LaunchLibrary(LaunchQtApp):
    """Launch Library Loader."""

    bl_idname = "wm.library_loader"
    bl_label = "Library..."
    _tool_name = "libraryloader"


class LaunchWorkFiles(LaunchQtApp):
    """Launch Avalon Work Files."""

    bl_idname = "wm.avalon_workfiles"
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
        unit_scale_settings = settings.get("unit_scale_settings")
        pipeline.set_unit_scale_from_settings(
            unit_scale_settings=unit_scale_settings)
        return {"FINISHED"}


class VersionUpWorkfile(LaunchQtApp):
    """Perform Incremental Save Workfile."""

    bl_idname = "wm.avalon_version_up_workfile"
    bl_label = "Version Up Workfile"

    def execute(self, context):
        version_up_current_workfile()
        return {"FINISHED"}


class TOPBAR_MT_avalon(bpy.types.Menu):
    """Avalon menu."""

    bl_idname = "TOPBAR_MT_avalon"
    bl_label = os.environ.get("AYON_MENU_LABEL")

    def draw(self, context):
        """Draw the menu in the UI."""

        layout = self.layout

        pcoll = PREVIEW_COLLECTIONS.get("avalon")
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
        layout.separator()
        layout.operator(LaunchWorkFiles.bl_idname, text="Work Files...")

def draw_avalon_menu(self, context):
    """Draw the Avalon menu in the top bar."""

    self.layout.menu(TOPBAR_MT_avalon.bl_idname)


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
    VersionUpWorkfile,
    TOPBAR_MT_avalon,
]


def register():
    "Register the operators and menu."

    pcoll = bpy.utils.previews.new()
    pyblish_icon_file = Path(__file__).parent / "icons" / "pyblish-32x32.png"
    pcoll.load("pyblish_menu_icon", str(pyblish_icon_file.absolute()), 'IMAGE')
    PREVIEW_COLLECTIONS["avalon"] = pcoll

    BlenderApplication.get_app()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_avalon_menu)


def unregister():
    """Unregister the operators and menu."""

    pcoll = PREVIEW_COLLECTIONS.pop("avalon")
    bpy.utils.previews.remove(pcoll)
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_avalon_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
