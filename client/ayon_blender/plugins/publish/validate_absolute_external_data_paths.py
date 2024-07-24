import bpy
import pyblish.api
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError
)



class ValidateAbsoluteExternalDataPaths(pyblish.api.InstancePlugin,
                                        OptionalPyblishPluginMixin):
    """Validates Absolute External Data Paths

    This validator checks if all external data paths are absolute
    to ensure the links would not be broke when publishing
    """

    label = "Validate Absolute External Data Paths"
    order = ValidateContentsOrder
    hosts = ["blender"]
    optional = True
    actions = [RepairAction]

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        object_type = type(bpy.data.objects)
        for attr in dir(bpy.data):
            collections = getattr(bpy.data, attr)
            if isinstance(collections, object_type):
                for data_block in collections:
                    if hasattr(data_block, "filepath") and data_block.filepath:
                        if data_block.filepath != bpy.path.abspath(data_block.filepath):
                            cls.log.error(f"Absolute external data path {data_block.filepath} "
                                          "is not absolute path")
                            invalid.append(data_block.filepath)
        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            self.log.debug("Skipping Validate Absolute External Data Paths...")
            return
        invalid = self.get_invalid(instance)
        if invalid:
            bullet_point_errors = "\n".join(
                "- {}".format(error) for error in invalid
            )
            report = (
                "External Data Paths are not absolute.\n\n"
                f"{bullet_point_errors}\n\n"
                "You can use repair action to fix it."
            )
            raise PublishValidationError(report, title="Relative External Data Paths")

    @classmethod
    def repair(cls, instance):
        return bpy.ops.file.make_paths_absolute()
