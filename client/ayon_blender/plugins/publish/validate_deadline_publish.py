import os

import bpy

from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_blender.api import plugin


class ValidateSceneRenderFilePath(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Validate Scene Render Output File Path is not empty.

    Validates `bpy.context.scene.render.filepath` is set to a valid directory.
    """
    order = ValidateContentsOrder
    families = ["render"]
    hosts = ["blender"]
    label = "Validate Scene Render Output"
    optional = True
    actions = [RepairAction]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        if not bpy.context.scene.render.filepath:
            raise PublishValidationError(
                message=(
                    "No render filepath set in the scene!"
                    "Use Repair action to fix the render filepath."
                ),
                title="No scene render filepath set"
            )

    @classmethod
    def repair(cls, instance):
        tmp_render_path = os.path.join(
            os.getenv("AYON_WORKDIR"), "renders", "tmp"
        )
        tmp_render_path = tmp_render_path.replace("\\", "/")
        os.makedirs(tmp_render_path, exist_ok=True)
        bpy.context.scene.render.filepath = f"{tmp_render_path}/"

        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)


class ValidateDeadlinePublish(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Validates Render File Directory is not the same in every submission

    Validates the render outputs of the `CompositorNodeOutputFile` node.
    """

    order = ValidateContentsOrder
    families = ["render"]
    hosts = ["blender"]
    label = "Validate Render Output for Deadline"
    optional = True
    actions = [RepairAction]

    # TODO: Fix validator - it should just validate against the pre-collected
    #  expected output files instead so that we do not need to duplicate the
    #  logic of exactly figuring out the output filepaths.

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            bullet_point_invalid_statement = "\n".join(
                "- {}".format(err) for err in invalid
            )
            report = (
                "Render Output has invalid values(s).\n\n"
                f"{bullet_point_invalid_statement}\n\n"
            )
            raise PublishValidationError(
                report,
                title="Invalid value(s) for Render Output")

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        output_node: "bpy.types.CompositorNodeOutputFile" = (
            instance.data["transientData"]["instance_node"]
        )
        if not output_node:
            msg = "No output node found in the compositor tree."
            invalid.append(msg)

        workfile_filepath: str = bpy.data.filepath
        file = os.path.basename(workfile_filepath)
        filename, ext = os.path.splitext(file)
        if filename not in output_node.base_path:
            msg = (
                "Render output folder doesn't match the blender scene name! "
                "Use Repair action to fix the folder file path."
            )
            invalid.append(msg)
        return invalid

    @classmethod
    def repair(cls, instance):
        """Update the render output path to include the scene name."""
        output_node: "bpy.types.CompositorNodeOutputFile" = (
            instance.data["transientData"]["instance_node"]
        )

        # TODO: Fix the repair logic below to not rely on the 'render_data'
        render_data = {}  # TODO: Fix
        aov_sep: str = render_data.get("aov_separator", "_")
        filename = os.path.basename(bpy.data.filepath)
        filename, ext = os.path.splitext(filename)
        is_multilayer: bool = render_data.get("multilayer_exr", True)
        orig_output_path = output_node.base_path
        if is_multilayer:
            render_folder = render_data.get("render_folder")
            output_dir = os.path.dirname(bpy.data.filepath)
            output_dir = os.path.join(output_dir, render_folder, filename)
            orig_output_dir = os.path.dirname(orig_output_path)
            new_output_dir = orig_output_path.replace(orig_output_dir,
                                                      output_dir)
        else:
            output_node_dir = os.path.dirname(orig_output_path)
            new_output_dir = os.path.join(output_node_dir, filename)

        output_node.base_path = new_output_dir
