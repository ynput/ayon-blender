import bpy
import inspect
import pyblish.api

from ayon_core.pipeline import (
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError
)


class ValidateNoLinkedObject(pyblish.api.InstancePlugin,
                             OptionalPyblishPluginMixin):
    """Validates object is not linked from other file.

    """

    label = "Validate No Linked Object"
    order = ValidateContentsOrder
    families = ["look"]
    hosts = ["blender"]
    optional = True
    actions = [RepairAction]

    @classmethod
    def get_invalid(cls, instance):
        """Get invalid objects in the instance.

        Args:
            instance (pyblish.api.Instance): The instance to validate.

        Returns:
            list: A list of invalid objects.
        """
        invalid = []
        for obj in instance:
            if not (
                isinstance(obj, bpy.types.Object)
                and hasattr(obj.data, "materials")
            ):
                continue
            if hasattr(obj, "library") and obj.library is not None:
                invalid.append(obj)
            for material in obj.data.materials:
                if hasattr(material, "library") and material.library is not None:
                    invalid.append(obj)

        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            self.log.debug("Skipping Validate No Linked Object.")
            return
        invalid = self.get_invalid(instance)
        if invalid:
            names = ", ".join(obj.name for obj in invalid)
            raise PublishValidationError(
                "Objects found in instance which are linked "
                f"to other files: {names}",
                title="No Linked Objects",
                description=self.get_description()
            )

    def get_description(self):
        return inspect.cleandoc("""
            ### Linked Objects Found
            Objects in the instance are linked to other files.
            Please make the objects local before publishing or
            use the repair action to make them local.
        """
        )

    @classmethod
    def repair(cls, instance):
        invalid_objects = cls.get_invalid(instance)
        for invalid_object in invalid_objects:
            invalid_object.make_local(clear_asset_data=True)
