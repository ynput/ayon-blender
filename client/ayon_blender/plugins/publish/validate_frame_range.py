import bpy
import pyblish.api

from ayon_core.pipeline import (
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    KnownPublishError
)

from ayon_blender.api.pipeline import get_frame_range


class ValidateFrameRange(pyblish.api.InstancePlugin,
                         OptionalPyblishPluginMixin):
    """Validates the frame ranges.

    This is an optional validator checking if the frame range on instance
    matches the frame range specified for the folder.

    It also validates render frame ranges of render layers.

    Repair action will change everything to match the folder frame range.

    This can be turned off by the artist to allow custom ranges.
    """

    label = "Validate Frame Range"
    order = ValidateContentsOrder
    families = ["render"]
    hosts = ["blender"]
    optional = True
    actions = [RepairAction]

    def process(self, instance):
        if not self.is_active(instance.data):
            self.log.debug("Skipping Validate Frame Range...")
            return

        frame_range = get_frame_range(instance.data["taskEntity"])
        scene = bpy.context.scene
        inst_frame_start = scene.frame_start
        inst_frame_end = scene.frame_end

        if inst_frame_start is None or inst_frame_end is None:
            raise KnownPublishError(
                "Missing frame start and frame end on "
                "instance to validate."
            )
        frame_start = frame_range["frameStart"]
        frame_end = frame_range["frameEnd"]
        errors = []
        if frame_start != inst_frame_start:
            errors.append(
                f"Start frame ({inst_frame_start}) on instance does not match " # noqa
                f"with the start frame ({frame_start}) set on the folder attributes. ")    # noqa
        if frame_end != inst_frame_end:
            errors.append(
                f"End frame ({inst_frame_end}) on instance does not match "
                f"with the end frame ({frame_end}) "
                "from the folder attributes. ")

        if errors:
            bullet_point_errors = "\n".join(
                "- {}".format(error) for error in errors
            )
            report = (
                "Frame range settings are incorrect.\n\n"
                f"{bullet_point_errors}\n\n"
                "You can use repair action to fix it."
            )
            raise PublishValidationError(report, title="Frame Range incorrect")

    @classmethod
    def repair(cls, instance):
        frame_range = get_frame_range(instance.data["taskEntity"])
        bpy.context.scene.frame_start = frame_range["frameStart"]
        bpy.context.scene.frame_end = frame_range["frameEnd"]
