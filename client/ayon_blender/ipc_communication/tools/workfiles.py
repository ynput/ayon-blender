from __future__ import annotations

import typing
from typing import Any


from ayon_core.host.interfaces import WorkfileInfo
from ayon_core.host import PublishedWorkfileInfo

from ayon_core.tools.workfiles.abstract import (
    AbstractWorkfilesFrontend,
    WorkareaFilepathResult,
    PublishedWorkfileWrap,
)
from ayon_core.tools.workfiles.widgets import WorkfilesToolWindow
from ayon_core.tools.common_models import (
    FolderItem,
    TaskItem,
    FolderTypeItem,
    TaskTypeItem,
)
from ayon_core.tools.common_models.users import UserItem

from ayon_core.lib.events import QueuedEventSystem

from .utils import execute_in_main_thread

if typing.TYPE_CHECKING:
    from ayon_blender.ipc_communication import IPCClient, RequestMessage


class BlenderWorkfilesFrontend(AbstractWorkfilesFrontend):
    window = None
    channel_name = "workfiles"

    def __init__(self, client: IPCClient):
        client.register_channel_handler(
            self.channel_name, self._handle_request
        )

        self._event_system = QueuedEventSystem()
        self._client: IPCClient = client

    def _handle_request(self, client: IPCClient, req: RequestMessage):
        if req.method == "show":
            execute_in_main_thread(self._show_window)
            return

        if req.method == "emit_event":
            self.emit_event(**req.params)

    def _show_window(self):
        if self.window is None:
            self.window = WorkfilesToolWindow(controller=self)

        self.window.show()

    def _trigger_method(
        self,
        method_name: str,
        params: dict[str, Any],
        wait: bool,
    ) -> Any | None:
        """Trigger method on backend.

        Args:
            method_name (str): Name of method to trigger.
            params (dict): Parameters for the method.
            wait (bool): Whether to wait for a response.

        Returns:
            Any: Result of the triggered method.

        """
        if not wait:
            self._client.send_request(self.channel_name, method_name, params)
            return None

        response = self._client.send_request_wait(
            self.channel_name, method_name, params
        )
        if not response.ok:
            raise Exception(response.error)
        return response.result

    def is_host_valid(self):
        """Host is valid for workfiles tool work.

        Returns:
            bool: True if host is valid.

        """
        return self._trigger_method(
            "is_host_valid", {}, True
        )

    def get_current_project_name(self):
        """Project name from current context of host.

        Returns:
            str: Name of project.

        """
        return self._trigger_method(
            "get_current_project_name", {}, True
        )

    def get_workfile_extensions(self):
        """Get possible workfile extensions.

        Defined by host implementation.

        Returns:
            Iterable[str]: List of extensions.

        """
        return self._trigger_method(
            "get_workfile_extensions", {}, True
        )

    def is_save_enabled(self):
        """Is workfile save enabled.

        Returns:
            bool: True if save is enabled.

        """
        return self._trigger_method(
            "is_save_enabled", {}, True
        )

    def set_save_enabled(self, enabled):
        """Enable or disabled workfile save.

        Args:
            enabled (bool): Enable save workfile when True.

        """
        self._trigger_method(
            "set_save_enabled",
            {"enabled": enabled},
            False
        )

    def get_window_subtitle(self) -> str | None:
        """Get window subtitle.

        Returns:
            str | None: Window subtitle.

        """
        return self._trigger_method(
            "get_window_subtitle", {}, True
        )

    def emit_event(self, topic, data, source):
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        """Register event callback.

        Listen for events with given topic.

        Args:
            topic (str): Name of topic.
            callback (Callable): Callback that will be called when event
                is triggered.

        """
        self._event_system.add_callback(topic, callback)

    def get_user_items_by_name(self):
        """Get user items available on AYON server.

        Returns:
            dict[str, UserItem]: User items by username.

        """
        data = self._trigger_method(
            "get_user_items_by_name", {}, True
        )
        return {
            key: UserItem.from_data(value)
            for key, value in data.items()
        }

    def get_folder_type_items(self, project_name, sender=None):
        """Folder type items for a project.

        This function may trigger events with topics
        'projects.folder_types.refresh.started' and
        'projects.folder_types.refresh.finished' which will contain 'sender'
        value in data.
        That may help to avoid re-refresh of items in UI elements.

        Args:
            project_name (str): Project name.
            sender (str): Who requested folder type items.

        Returns:
            list[FolderTypeItem]: Folder type information.

        """
        data = self._trigger_method(
            "get_folder_type_items",
            {"project_name": project_name, "sender": sender},
            True
        )
        return {
            key: FolderTypeItem.from_data(value)
            for key, value in data.items()
        }

    def get_task_type_items(self, project_name, sender=None):
        """Task type items for a project.

        This function may trigger events with topics
        'projects.task_types.refresh.started' and
        'projects.task_types.refresh.finished' which will contain 'sender'
        value in data.
        That may help to avoid re-refresh of items in UI elements.

        Args:
            project_name (str): Project name.
            sender (str): Who requested task type items.

        Returns:
            list[TaskTypeItem]: Task type information.

        """
        data = self._trigger_method(
            "get_task_type_items",
            {"project_name": project_name, "sender": sender},
            True
        )
        return {
            key: TaskTypeItem.from_data(value)
            for key, value in data.items()
        }

    # Host information
    def get_workfile_extensions(self):
        """Each host can define extensions that can be used for workfile.

        Returns:
            List[str]: File extensions that can be used as workfile for
                current host.

        """
        return self._trigger_method(
            "get_workfile_extensions", {}, True
        )

    # Selection information
    def get_selected_folder_id(self):
        """Currently selected folder id.

        Returns:
            Union[str, None]: Folder id or None if no folder is selected.

        """
        return self._trigger_method(
            "get_selected_folder_id", {}, True
        )

    def set_selected_folder(self, folder_id):
        """Change selected folder.

        This deselects currently selected task.

        Args:
            folder_id (Union[str, None]): Folder id or None if no folder
                is selected.

        """
        return self._trigger_method(
            "set_selected_folder", {"folder_id": folder_id}, True
        )

    def get_selected_task_id(self):
        """Currently selected task id.

        Returns:
            Union[str, None]: Task id or None if no folder is selected.

        """
        return self._trigger_method(
            "get_selected_task_id", {}, True
        )

    def get_selected_task_name(self):
        """Currently selected task name.

        Returns:
            Union[str, None]: Task name or None if no folder is selected.
        """
        return self._trigger_method(
            "get_selected_task_name", {}, True
        )

    def set_selected_task(self, task_id, task_name):
        """Change selected task.

        Args:
            task_id (Union[str, None]): Task id or None if no task
                is selected.
            task_name (Union[str, None]): Task name or None if no task
                is selected.

        """
        return self._trigger_method(
            "set_selected_task",
            {"task_id": task_id, "task_name": task_name},
            False
        )

    def get_selected_workfile_path(self):
        """Currently selected workarea workile.

        Returns:
            Union[str, None]: Selected workfile path.

        """
        return self._trigger_method(
            "get_selected_workfile_path", {}, True
        )

    def set_selected_workfile_path(
        self, rootless_path, path, workfile_entity_id
    ):
        """Change selected workfile path.

        Args:
            rootless_path (Union[str, None]): Selected workfile rootless path.
            path (Union[str, None]): Selected workfile path.
            workfile_entity_id (Union[str, None]): Workfile entity id.

        """
        return self._trigger_method(
            "set_selected_workfile_path",
            {
                "rootless_path": rootless_path,
                "path": path,
                "workfile_entity_id": workfile_entity_id
            },
            False
        )

    def get_selected_representation_id(self):
        """Currently selected workfile representation id.

        Returns:
            Union[str, None]: Representation id or None if no representation
                is selected.

        """
        return self._trigger_method(
            "get_selected_representation_id", {}, True
        )

    def set_selected_representation_id(self, representation_id):
        """Change selected representation.

        Args:
            representation_id (Union[str, None]): Selected workfile
                representation id.

        """
        return self._trigger_method(
            "set_selected_representation_id",
            {"representation_id": representation_id},
            False
        )

    def get_selected_context(self):
        """Obtain selected context.

        Returns:
            dict[str, Union[str, None]]: Selected context.

        """
        return self._trigger_method(
            "get_selected_context", {}, True
        )

    def set_expected_selection(
        self,
        folder_id,
        task_name,
        workfile_name=None,
        representation_id=None
    ):
        """Define what should be selected in UI.

        Expected selection provide a way to define/change selection of
        sequential UI elements. For example, if folder and task should be
        selected a task element should wait until folder element has selected
        folder.

        Triggers 'expected_selection.changed' event.

        Args:
            folder_id (str): Folder id.
            task_name (str): Task name.
            workfile_name (Optional[str]): Workfile name. Used for workarea
                files UI element.
            representation_id (Optional[str]): Representation id. Used for
                published filed UI element.

        """
        self._trigger_method(
            "set_expected_selection",
            {
                "folder_id": folder_id,
                "task_name": task_name,
                "workfile_name": workfile_name,
                "representation_id": representation_id
            },
            False
        )

    def get_expected_selection_data(self):
        """Data of expected selection.

        TODOs:
            Return defined object instead of dict.

        Returns:
            dict[str, Any]: Expected selection data.

        """
        self._trigger_method(
            "get_expected_selection_data", {}, True
        )

    def expected_folder_selected(self, folder_id):
        """Expected folder was selected in UI.

        Args:
            folder_id (str): Folder id which was selected.

        """
        self._trigger_method(
            "expected_folder_selected",
            {"folder_id": folder_id},
            False
        )

    def expected_task_selected(self, folder_id, task_name):
        """Expected task was selected in UI.

        Args:
            folder_id (str): Folder id under which task is.
            task_name (str): Task name which was selected.

        """
        self._trigger_method(
            "expected_task_selected",
            {"folder_id": folder_id, "task_name": task_name},
            False
        )

    def expected_representation_selected(
        self, folder_id, task_name, representation_id
    ):
        """Expected representation was selected in UI.

        Args:
            folder_id (str): Folder id under which representation is.
            task_name (str): Task name under which representation is.
            representation_id (str): Representation id which was selected.

        """
        self._trigger_method(
            "expected_representation_selected",
            {
                "folder_id": folder_id,
                "task_name": task_name,
                "representation_id": representation_id
            },
            False
        )

    def expected_workfile_selected(self, folder_id, task_name, workfile_name):
        """Expected workfile was selected in UI.

        Args:
            folder_id (str): Folder id under which workfile is.
            task_name (str): Task name under which workfile is.
            workfile_name (str): Workfile filename which was selected.

        """
        self._trigger_method(
            "expected_workfile_selected",
            {
                "folder_id": folder_id,
                "task_name": task_name,
                "workfile_name": workfile_name
            },
            False
        )

    def go_to_current_context(self):
        """Set expected selection to current context."""

        self._trigger_method("go_to_current_context", {}, False)

    def get_folder_items(self, project_name, sender):
        """Folder items to visualize project hierarchy.

        This function may trigger events 'folders.refresh.started' and
        'folders.refresh.finished' which will contain 'sender' value in data.
        That may help to avoid re-refresh of folder items in UI elements.

        Args:
            project_name (str): Project name for which are folders requested.
            sender (str): Who requested folder items.

        Returns:
            list[FolderItem]: Minimum possible information needed
                for visualisation of folder hierarchy.

        """
        folder_items = self._trigger_method(
            "get_folder_items",
            {"project_name": project_name, "sender": sender},
            True
        )
        return [
            FolderItem.from_data(item)
            for item in folder_items
        ]

    def get_task_items(self, project_name, folder_id, sender):
        """Task items.

        This function may trigger events 'tasks.refresh.started' and
        'tasks.refresh.finished' which will contain 'sender' value in data.
        That may help to avoid re-refresh of task items in UI elements.

        Args:
            project_name (str): Project name for which are tasks requested.
            folder_id (str): Folder ID for which are tasks requested.
            sender (str): Who requested task items.

        Returns:
            list[TaskItem]: Minimum possible information needed
                for visualisation of tasks.

        """
        task_items = self._trigger_method(
            "get_task_items",
            {
                "project_name": project_name,
                "folder_id": folder_id,
                "sender": sender
            },
            True
        )
        return [
            TaskItem.from_data(item)
            for item in task_items
        ]

    def has_unsaved_changes(self):
        """Has host unsaved change in currently running session.

        Returns:
            bool: Has unsaved changes.

        """
        return self._trigger_method(
            "has_unsaved_changes", {}, True
        )

    def get_workarea_dir_by_context(self, folder_id, task_id):
        """Get workarea directory by context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            str: Workarea directory.

        """
        return self._trigger_method(
            "get_workarea_dir_by_context",
            {"folder_id": folder_id, "task_id": task_id},
            True
        )

    def get_workarea_file_items(self, folder_id, task_name, sender=None):
        """Get workarea file items.

        Args:
            folder_id (str): Folder id.
            task_name (str): Task name.
            sender (Optional[str]): Who requested workarea file items.

        Returns:
            list[WorkfileInfo]: List of workarea file items.

        """
        return self._trigger_method(
            "get_workarea_file_items",
            {
                "folder_id": folder_id,
                "task_name": task_name,
                "sender": sender
            },
            True
        )

    def get_workarea_save_as_data(self, folder_id, task_id):
        """Prepare data for Save As operation.

        Todos:
            Return defined object instead of dict.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            dict[str, Any]: Data for Save As operation.

        """
        return self._trigger_method(
            "get_workarea_save_as_data",
            {"folder_id": folder_id, "task_id": task_id},
            True
        )

    def fill_workarea_filepath(
        self,
        folder_id,
        task_id,
        extension,
        use_last_version,
        version,
        comment,
    ):
        """Calculate workfile path for passed context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            extension (str): File extension.
            use_last_version (bool): Use last version.
            version (int): Version used if 'use_last_version' if 'False'.
            comment (str): User's comment (subversion).

        Returns:
            WorkareaFilepathResult: Result of the operation.

        """
        data = self._trigger_method(
            "fill_workarea_filepath",
            {
                "folder_id": folder_id,
                "task_id": task_id,
                "extension": extension,
                "use_last_version": use_last_version,
                "version": version,
                "comment": comment,
            },
            True
        )
        return WorkareaFilepathResult(
            root=data["root"],
            filename=data["filename"],
            exists=data["exists"],
            filepath=data["filepath"]
        )

    def get_published_file_items(self, folder_id: str, task_id: str):
        """Get published file items.

        Args:
            folder_id (str): Folder id.
            task_id (Union[str, None]): Task id.

        Returns:
            list[PublishedWorkfileInfo]: List of published file items.

        """
        data = self._trigger_method(
            "get_published_file_items",
            {"folder_id": folder_id, "task_id": task_id},
            True
        )
        return [PublishedWorkfileInfo.from_data(item) for item in data]

    def get_published_workfile_info(
        self,
        folder_id: str | None,
        representation_id: str | None,
    ) -> PublishedWorkfileWrap:
        """Get published workfile info by representation ID.

        Args:
            folder_id (Optional[str]): Folder id.
            representation_id (Optional[str]): Representation id.

        Returns:
            PublishedWorkfileWrap: Published workfile info or None
                if not found.

        """
        data = self._trigger_method(
            "get_published_workfile_info",
            {"folder_id": folder_id, "representation_id": representation_id},
            True
        )
        return PublishedWorkfileWrap(
            info=data["info"],
            comment=data["comment"],
        )

    def get_workfile_info(self, folder_id, task_id, rootless_path):
        """Workfile info from database.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            rootless_path (str): Workfile path.

        Returns:
            Optional[WorkfileInfo]: Workfile info or None if was passed
                invalid context.

        """
        data = self._trigger_method(
            "get_workfile_info",
            {
                "folder_id": folder_id,
                "task_id": task_id,
                "rootless_path": rootless_path
             },
            True
        )
        if data is None:
            return None
        return WorkfileInfo.from_data(data)

    def save_workfile_info(
        self,
        task_id,
        rootless_path,
        version=None,
        comment=None,
        description=None,
    ):
        """Save workfile info to database.

        At this moment the only information which can be saved about
            workfile is 'description'.

        If value of 'version', 'comment' or 'description' is 'None' it is not
            added/updated to entity.

        Args:
            task_id (str): Task id.
            rootless_path (str): Rootless workfile path.
            version (Optional[int]): Version of workfile.
            comment (Optional[str]): User's comment (subversion).
            description (Optional[str]): Workfile description.

        """
        self._trigger_method(
            "save_workfile_info",
            {
                "task_id": task_id,
                "rootless_path": rootless_path,
                "version": version,
                "comment": comment,
                "description": description
            },
            False
        )

    def reset(self):
        """Reset everything, models, ui etc.

        Triggers 'controller.reset.started' event at the beginning and
        'controller.reset.finished' at the end.

        """
        self._trigger_method("reset", {}, False)

    def open_workfile(self, folder_id, task_id, filepath):
        """Open a workfile for context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            filepath (str): Workfile path.

        """
        self._trigger_method(
            "open_workfile",
            {
                "folder_id": folder_id,
                "task_id": task_id,
                "filepath": filepath
            },
            False
        )

    def save_current_workfile(self):
        """Save state of current workfile."""

        self._trigger_method("save_current_workfile", {}, False)

    def save_as_workfile(
        self,
        folder_id,
        task_id,
        rootless_workdir,
        workdir,
        filename,
        version,
        comment,
        description,
    ):
        """Save current state of workfile to workarea.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            rootless_workdir (str): Workarea directory.
            filename (str): Workarea filename.
            template_key (str): Template key used to get the workdir
                and filename.
            version (Optional[int]): Version of workfile.
            comment (Optional[str]): User's comment (subversion).
            description (Optional[str]): Workfile description.

        """
        self._trigger_method(
            "save_as_workfile",
            {
                "folder_id": folder_id,
                "task_id": task_id,
                "rootless_workdir": rootless_workdir,
                "workdir": workdir,
                "filename": filename,
                "version": version,
                "comment": comment,
                "description": description
            },
            False
        )

    def copy_workfile_representation(
        self,
        representation_id,
        representation_filepath,
        folder_id,
        task_id,
        workdir,
        filename,
        rootless_workdir,
        version,
        comment,
        description,
    ):
        """Action to copy published workfile representation to workarea.

        Triggers 'copy_representation.started' event on start and
        'copy_representation.finished' event with '{"failed": bool}'.

        Args:
            representation_id (str): Representation id.
            representation_filepath (str): Path to representation file.
            folder_id (str): Folder id.
            task_id (str): Task id.
            workdir (str): Workarea directory.
            filename (str): Workarea filename.
            rootless_workdir (str): Rootless workdir.
            version (int): Workfile version.
            comment (str): User's comment (subversion).
            description (str): Description note.

        """
        self._trigger_method(
            "copy_workfile_representation",
            {
                "representation_id": representation_id,
                "representation_filepath": representation_filepath,
                "folder_id": folder_id,
                "task_id": task_id,
                "workdir": workdir,
                "filename": filename,
                "rootless_workdir": rootless_workdir,
                "version": version,
                "comment": comment,
                "description": description
            },
            False
        )

    def duplicate_workfile(
        self,
        folder_id,
        task_id,
        src_filepath,
        rootless_workdir,
        workdir,
        filename,
        description,
        version,
        comment
    ):
        """Duplicate workfile.

        Workfiles is not opened when done.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            src_filepath (str): Source workfile path.
            rootless_workdir (str): Rootless workdir.
            workdir (str): Destination workdir.
            filename (str): Destination filename.
            version (int): Workfile version.
            comment (str): User's comment (subversion).
            description (str): Workfile description.
        """
        self._trigger_method(
            "duplicate_workfile",
            {
                "folder_id": folder_id,
                "task_id": task_id,
                "src_filepath": src_filepath,
                "rootless_workdir": rootless_workdir,
                "workdir": workdir,
                "filename": filename,
                "version": version,
                "comment": comment,
                "description": description
            },
            False
        )
