from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable

EMPTY = object()


@dataclass
class MainThreadItem:
    """Structure to store information about callback in main thread.

    Item should be used to execute callback in main thread which may be needed
    for execution of Qt objects.

    Item store callback (callable variable), arguments and keyword arguments
    for the callback. Item hold information about it's process.
    """
    callback: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    done = False
    exception = EMPTY
    result = EMPTY
    sleep_time: float = 0.1

    def execute(self):
        """Execute callback and store its result.

        Method must be called from main thread. Item is marked as `done`
        when callback execution finished. Store output of callback of exception
        information when callback raises one.
        """
        if self.done:
            return

        callback = self.callback
        args = self.args
        kwargs = self.kwargs
        try:
            result = callback(*args, **kwargs)
            self.result = result

        except Exception as exc:
            self.exception = exc

        finally:
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
            time.sleep(self.sleep_time)

        if self.exception is EMPTY:
            return self.result
        raise self.exception


class _LocalData:
    main_thread: threading.Thread = threading.current_thread()
    main_thread_callbacks: deque[MainThreadItem] = deque()


def add_main_thread_item(main_thread_item: MainThreadItem) -> None:
    _LocalData.main_thread_callbacks.append(main_thread_item)


def execute_in_main_thread(func: Callable, *args, **kwargs) -> MainThreadItem:
    main_thread_item = MainThreadItem(func, args, kwargs)
    if threading.current_thread() is _LocalData.main_thread:
        main_thread_item.execute()
    else:
        add_main_thread_item(main_thread_item)
    return main_thread_item


def process_main_thread_callbacks() -> None:
    if not _LocalData.main_thread_callbacks:
        return

    for _ in range(len(_LocalData.main_thread_callbacks)):
        item = _LocalData.main_thread_callbacks.popleft()
        item.execute()
        if item.exception is EMPTY:
            continue

        # TODO handle error
        # _clc, val, tb = item.exception
        # msg = str(val)
        # detail = "\n".join(traceback.format_exception(_clc, val, tb))
        # dialog = QtWidgets.QMessageBox(
        #     QtWidgets.QMessageBox.Warning,
        #     "Error",
        #     msg)
        # dialog.setMinimumWidth(500)
        # dialog.setDetailedText(detail)
        # dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        # dialog.setStyleSheet(load_stylesheet())
        # # Ensure the dialog stays on top and is properly focused
        # dialog.setWindowFlags(
        #     dialog.windowFlags() |
        #     QtCore.Qt.WindowStaysOnTopHint |
        #     QtCore.Qt.Dialog
        # )
        # dialog.raise_()
        # dialog.activateWindow()
        # dialog.open()
