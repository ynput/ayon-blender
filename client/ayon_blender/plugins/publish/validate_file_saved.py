from typing import Optional
import bpy

import pyblish.api
import semver

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError
)
from ayon_blender.api import plugin


def get_ayon_core_version() -> Optional[semver.VersionInfo]:
    try:
        from ayon_core import __version__ as core_version
    except ImportError:
        return None
    return semver.VersionInfo.parse(core_version)


class SaveWorkfileAction(pyblish.api.Action):
    """Save Workfile."""
    label = "Save Workfile"
    on = "failed"
    icon = "save"

    def process(self, context, plugin):
        bpy.ops.wm.ayon_workfiles()


class ValidateFileSaved(
    plugin.BlenderContextPlugin,
    OptionalPyblishPluginMixin
):
    """Validate that the workfile has been saved.

    If ayon-core version is >=1.4.1, this validation will be ignored due to
    an equivalent validation implementation in ayon-core.
    """

    order = pyblish.api.ValidatorOrder - 0.01
    hosts = ["blender"]
    label = "Validate File Saved (Legacy)"
    optional = False
    actions = [SaveWorkfileAction]

    def process(self, context):
        if not self.is_active(context.data):
            return

        if context.data.get("currentFile"):
            # File has been saved at least once and has a filename
            return

        # We only invalidate here if an older AYON core version is used.
        ayon_core_version = get_ayon_core_version()
        if ayon_core_version is None:
            self.log.warning(
                "Unable to parse ayon-core version. Skipping validation."
            )
            return

        # Check if ayon-core version is >=1.4.1, if so this validation is
        # superseded by ValidateCurrentSaveFile in ayon-core.
        if ayon_core_version > semver.VersionInfo(1, 4, 0):
            self.log.debug(
                "Skipping workfile saved validation in favor of equivalent"
                f"validation in ayon-core {ayon_core_version}"
            )
            return

        if not context.data["currentFile"]:
            # File has not been saved at all and has no filename
            raise PublishValidationError(
                "Current workfile has not been saved yet.\n"
                "Save the workfile before continuing.",
                title="Validate File Saved",
            )
