import bpy
import inspect
import pyblish.api
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    RepairContextAction,
    ValidateContentsOrder,
    PublishValidationError
)


class ValidateAbsoluteDataBlockPaths(pyblish.api.ContextPlugin,
                                     OptionalPyblishPluginMixin):
    """Validates Absolute Data Block Paths

    This validator checks if all external data paths are absolute
    to ensure the links would not be broken when publishing
    """

    label = "Validate Absolute Data Block Paths"
    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["workfile"]
    optional = True
    actions = [RepairContextAction]

    @classmethod
    def get_invalid(cls, context):
        invalid = []
        object_type = type(bpy.data.objects)
        for attr in dir(bpy.data):
            collections = getattr(bpy.data, attr)
            if not isinstance(collections, object_type):
                continue
            for data_block in collections:
                if not hasattr(data_block, "filepath"):
                    continue
                if not data_block.filepath:
                    continue
                if data_block.filepath == bpy.path.abspath(data_block.filepath):
                    continue

                cls.log.error(f"Data block filepath {data_block.filepath} "
                                "is not absolute path")
                invalid.append(data_block.filepath)
        return invalid

    def process(self, context):
        if not self.is_active(context.data):
            self.log.debug("Skipping Validate Absolute Data Block Paths...")
            return
        invalid = self.get_invalid(context)
        if invalid:
            bullet_point_errors = "\n".join(
                "- {}".format(error) for error in invalid
            )
            raise PublishValidationError(
                "Invalid Data block filepaths",
                title="Relative Data block filepaths",
                description=self.get_description(bullet_point_errors)
            )

    @classmethod
    def get_description(cls, bullet_point_errors):
        return inspect.cleandoc(f"""
            ### Data block filepaths are invalid

            Data block filepaths are not in absolute paths:
            #### {bullet_point_errors}\n
            You can use repair action to make the data block filepaths absolute.

        """)

    @classmethod
    def repair(cls, context):
        return bpy.ops.file.make_paths_absolute()
