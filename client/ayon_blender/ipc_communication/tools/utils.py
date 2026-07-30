from __future__ import annotations

import collections

from qtpy import QtCore

from ayon_core.lib import Logger


class WrappedCallbackItem:
    """Structure to store information about callback and args/kwargs for it.

    Item can be used to execute callback in main thread which may be needed
    for execution of Qt objects.

    Item store callback (callable variable), arguments and keyword arguments
    for the callback. Item hold information about it's process.
    """
    not_set = object()
    log = Logger.get_logger("WrappedCallbackItem")

    def __init__(self, callback, *args, **kwargs):
        self.done = False
        self.exception = self.not_set
        self.result = self.not_set
        self._callback = callback
        self._args = args
        self._kwargs = kwargs

    def __call__(self):
        self.execute()

    def execute(self):
        """Execute callback and store its result.

        Method must be called from main thread. Item is marked as `done`
        when callback execution finished. Store output of callback of exception
        information when callback raises one.
        """
        if self.done:
            self.log.warning("- item is already processed")
            return

        try:
            result = self._callback(*self._args, **self._kwargs)
            self.result = result

        except Exception as exc:
            self.exception = exc

        finally:
            self.done = True


def execute_in_main_thread(callback, *args, **kwargs):
    if isinstance(callback, WrappedCallbackItem):
        item = callback
    else:
        item = WrappedCallbackItem(callback, *args, **kwargs)

    _MainThreadHelper.queue.append(item)


def process_queue():
    """Process all items in the queue.

    Method must be called from main thread. All items in the queue are
    executed and removed from the queue.
    """
    for _ in range(len(_MainThreadHelper.queue)):
        item = _MainThreadHelper.queue.popleft()
        item.execute()


class _MainThreadHelper:
    queue = collections.deque()
    timer = QtCore.QTimer()
    timer.setInterval(300)
    timer.timeout.connect(process_queue)


def start_main_thread_helper():
    """Start main thread helper.

    Method must be called from main thread. Start timer which will process
    queue of items to be executed in main thread.
    """
    _MainThreadHelper.timer.start()
