from typing import Optional
from pathlib import Path
import inspect
import os

import bpy
import pyblish.api

from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_blender.api import plugin, render_lib


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
    label = "Validate Scene Render Filepath"
    optional = True
    actions = [RepairAction]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        if not bpy.data.filepath:
            # Blender workfile is not saved, so we can't validate the
            # scene render filepath correctly.
            self.log.warning(
                "Blender workfile is not saved. "
                "Please save the workfile before publishing."
            )
            return

        expected_render_path = self._get_expected_render_path(instance)
        if (
            Path(bpy.context.scene.render.filepath.rstrip("/")) !=
            Path(expected_render_path)
        ):
            self.log.warning(
                f"Current scene output: {bpy.context.scene.render.filepath} "
            )
            self.log.info(f"Expected scene output: {expected_render_path}")
            raise PublishValidationError(
                message=(
                    "Scene Render filepath not set correctly. "
                    "Use Repair action to fix the render filepath."
                ),
                description=self.get_description(),
                title="Invalid scene render filepath set"
            )

        if not bpy.context.scene.render.use_overwrite:
            raise PublishValidationError(
                title="Scene render overwrite is disabled",
                message="Scene Render overwrite is disabled.",
                description=(
                    "### Scene Render Overwrite Disabled\n\n"
                    "It's recommended to enable this so that requeue on farm "
                    "will not skip rendering just because the file already "
                    "exists. Use Repair action to enable overwrite."
                )
            )

    @staticmethod
    def _get_expected_render_path(instance: pyblish.api.Instance) -> str:
        """Get the expected render path based on the current scene."""
        project_settings = instance.context.data["project_settings"]
        return render_lib.get_tmp_scene_render_output_path(project_settings)

    @classmethod
    def repair(cls, instance):
        project_settings = instance.context.data["project_settings"]
        render_lib.set_tmp_scene_render_output_path(project_settings)

        # Force enable overwrite so re-queue on the farm does not stop just
        # because a file already exists.
        bpy.context.scene.render.use_overwrite = True

        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)

    @staticmethod
    def get_description():
        return inspect.cleandoc("""
        ### Scene render filepath invalid
        
        The scene output filepath is set to incorrectly.
        
        We are enforcing the scene output filepath to be set to a `tmp`
        file inside the renders folder of the work directory. This is because
        the scene render output is unused by AYON since we only manage the
        Compositor's Output File node for render outputs. The scene wide render
        outputs can't be disabled, so we set it to a temporary filepath.
        
        The temporary filepath is unique per workfile version to avoid 
        conflicts of different workfile versions being rendered simultaneous 
        on the farm and resulting in write locks on the same file.
        """)


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
    label = "Validate Compositor Node File Output Paths"
    optional = True
    actions = [RepairAction]

    # TODO: Fix validator - it should just validate against the pre-collected
    #  expected output files instead so that we do not need to duplicate the
    #  logic of exactly figuring out the output filepaths.

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid_error_message = self.get_invalid(instance)
        if invalid_error_message:
            raise PublishValidationError(
                invalid_error_message,
                title="Invalid compositor render outputs",
                description=self.get_description()
            )

    @classmethod
    def get_invalid(cls, instance) -> Optional[str]:
        output_node: "bpy.types.CompositorNodeOutputFile" = (
            instance.data["transientData"]["instance_node"]
        )
        if not output_node:
            return "No output node found in the compositor tree."

        workfile_filepath: str = bpy.data.filepath
        if not workfile_filepath:
            cls.log.warning("No workfile scene filepath set. "
                            "Please save the workfile.")
            return None

        workfile_filename = os.path.basename(workfile_filepath)
        workfile_filename_no_ext, _ext = os.path.splitext(workfile_filename)
        cls.log.debug(
            f"Found compositor output node '{output_node.name}' "
            f"with base path: {output_node.base_path}")
        if workfile_filename_no_ext not in output_node.base_path:
            return (
                "Render output folder does not include workfile name: "
                f"{workfile_filename_no_ext}.\n\n"
                "Use Repair action to fix the render base filepath."
            )

        return None

    @classmethod
    def repair(cls, instance):
        """Update the render output path to include the scene name."""
        output_node: "bpy.types.CompositorNodeOutputFile" = (
            instance.data["transientData"]["instance_node"]
        )

        # Check whether CompositorNodeOutputFile is rendering to multilayer EXR
        file_format: str = output_node.format.file_format
        is_multilayer: bool = file_format == "OPEN_EXR_MULTILAYER"

        filename = os.path.basename(bpy.data.filepath)
        filename, ext = os.path.splitext(filename)
        orig_output_path = output_node.base_path
        if is_multilayer:
            # If the output node is a multilayer EXR then the base path
            # includes the render filename like `Main_beauty.####.exr`
            # So we split that off, and assume that the parent folder to
            # the filename is the workfile filename named folder.
            render_folder, render_filename = os.path.split(orig_output_path)
            output_node_dir = os.path.dirname(render_folder)
            new_output_dir = os.path.join(output_node_dir,
                                          filename,
                                          render_filename)
        else:
            output_node_dir = os.path.dirname(orig_output_path)
            new_output_dir = os.path.join(output_node_dir, filename)

        output_node.base_path = new_output_dir

    @staticmethod
    def get_description():
        return inspect.cleandoc("""
        ### Compositor Output Filepaths Invalid
        
        The Output File node in the Compositor has invalid output paths.
        
        The filepaths must:
        - Include the workfile name in the output path, this is to ensure
          unique render paths for each workfile version.
        - Not start with a single slash `/`. If you meant to use a relative
          path then use `//` at the start of the path.
        """)
