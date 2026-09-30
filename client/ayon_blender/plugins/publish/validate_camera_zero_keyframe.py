from typing import List

import bpy
from bpy_extras import anim_utils

import ayon_blender.api.action
from ayon_blender.api import plugin
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)


def get_action_fcurves(animation_data: bpy.types.AnimData) -> List:
    """Return the F-Curves of the action assigned to the animation data.

    Blender 4.4+ uses slotted actions and Blender 5.0 removed
    `Action.fcurves`, so get the F-Curves from the assigned slot instead.
    """
    action = animation_data.action
    if hasattr(anim_utils, "action_get_channelbag_for_slot"):
        channelbag = anim_utils.action_get_channelbag_for_slot(
            action, animation_data.action_slot
        )
        return list(channelbag.fcurves) if channelbag else []
    return list(action.fcurves)


class ValidateCameraZeroKeyframe(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Camera must have a keyframe at frame 0.

    Unreal shifts the first keyframe to frame 0. Forcing the camera to have
    a keyframe at frame 0 will ensure that the animation will be the same
    in Unreal and Blender.
    """

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["camera"]
    label = "Zero Keyframe"
    actions = [ayon_blender.api.action.SelectInvalidAction]

    @staticmethod
    def get_invalid(instance) -> List:
        invalid = []
        for obj in instance:
            if isinstance(obj, bpy.types.Object) and obj.type == "CAMERA":
                if obj.animation_data and obj.animation_data.action:
                    frames = {
                        keyframe.co[0]
                        for fcurve in get_action_fcurves(obj.animation_data)
                        for keyframe in fcurve.keyframe_points
                    }
                    if frames and min(frames) != 0.0:
                        invalid.append(obj)
        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            names = ", ".join(obj.name for obj in invalid)
            raise PublishValidationError(
                f"Camera must have a keyframe at frame 0: {names}"
            )
