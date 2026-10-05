from typing import List

import bpy

from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError
)
import ayon_blender.api.action
from ayon_blender.api import plugin


class ValidateMeshHasUvs(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate that the current mesh has UV's."""

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["model"]
    label = "Mesh Has UVs"
    actions = [ayon_blender.api.action.SelectInvalidAction]
    optional = True

    @staticmethod
    def has_uvs(obj: bpy.types.Object) -> bool:
        """Check if an object has uv's."""
        return bool(obj.data.uv_layers)

    @classmethod
    def get_invalid(cls, instance) -> List:
        invalid = []
        for obj in instance:
            if isinstance(obj, bpy.types.Object) and obj.type == 'MESH':
                if obj.mode != "OBJECT":
                    cls.log.warning(
                        f"Mesh object {obj.name} should be in 'OBJECT' mode"
                        " to be properly checked."
                    )
                if not cls.has_uvs(obj):
                    invalid.append(obj)
        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                f"Meshes found in instance without valid UV's: {invalid}"
            )
