from typing import Optional
from pathlib import Path
import inspect
import os
import re

import bpy
import pyblish.api

from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_blender.api import plugin, render_lib


def fix_filename(path: str, extension: Optional[str] = None) -> str:
    """Ensure the filename ends with `.{frame}.{ext}`.

    It's also fine for the path to not specify frame number
    and extension, in which case Blender will automatically add it.

    Examples:
        >>> fix_filename("folder/beauty")
        'folder/beauty.'

        >>> fix_filename("folder/beauty#.exr")
        'folder/beauty.#.exr'

        >>> fix_filename("test.exr")
        'test.####.exr'

        >>> fix_filename("test.", extension=".exr")
        'test.'

        >>> fix_filename("test.####.aov.exr", extension=".png")
        'test.aov.####.png'

    Arguments:
        path (str): The file path to fix.
        extension (Optional[str]): The file extension to use. If not provided,
            it will be inferred from the filename if it has an extension.
            If the `path` does not have an extension, the `extensions` argument
            will remain unused. The extension should start with a dot, e.g.
            `.exr`.

    Returns:
        str: The fixed file path with the filename ending in `.{frame}.{ext}`.

    """
    folder, filename = os.path.split(path)

    # Get characteristics of the current filename to determine what
    # we want to preserve.
    has_extension: bool = bool(re.search(r".*\.[A-Za-z]+$", filename))
    if extension is None and has_extension:
        extension = os.path.splitext(filename)[-1]
    has_frame_token: bool = "#" in filename
    frame_padding: int = filename.count("#") or 4

    # Remove extension and frame tokens
    if has_extension:
        filename = os.path.splitext(filename)[0]
    if has_frame_token:
        # remove any dots with frame tokens to avoid e.g. `test.####.aov.exr`
        # becoming `test..aov.exr`
        filename = filename.replace(".#", "")
        filename = filename.replace("#", "")

    # Remove any trailing dots or underscores
    filename = filename.rstrip("._")

    filename += "."  # Ensure there's a dot before the frame number
    if has_extension or has_frame_token:
        filename += f"{'#' * frame_padding}"
    if has_extension:
        filename += extension

    return os.path.join(folder, filename)


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
            Path(bpy.context.scene.render.filepath) !=
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


class ValidateCompositorNodeFileOutputPaths(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Validate output render paths from the Compositor Node Output File.

    This validator checks that the render output paths set in the
    `CompositorNodeOutputFile` adhere to a few strict requirements:
    - The output base path must include the workfile name in the output path.
    - The output filename must end with `.{frame}.{ext}` where it is fine
      if the path on the node is set as `filename.` because if frame number
      and extension are missing Blender will automatically append them.
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

        workfile_filepath: str = bpy.data.filepath
        if not workfile_filepath:
            cls.log.warning("No workfile scene filepath set. "
                            "Please save the workfile.")
            return None

        workfile_filename = os.path.basename(workfile_filepath)
        workfile_filename_no_ext, _ext = os.path.splitext(workfile_filename)

        # Get expected files per AOV
        expected_files: dict[str, list[str]] = (
            instance.data["expectedFiles"][0]
        )

        # For each AOV output check the output filenames as they must end with
        # `.{frame}.{ext}` where the frame is a number and ext is the extension
        for _aov, output_files in expected_files.items():
            first_file = output_files[0]

            # Ensure filename ends with `.{frame}.{ext}` by checking whether
            file_no_ext = os.path.splitext(first_file)[0]
            if not file_no_ext[-1].isdigit():
                cls.log.warning(
                    f"Output file '{first_file}' does not end with "
                    "`.{frame}.{extension}`."
                )
                return (
                    "Output file does not contain a frame number before the "
                    "extension."
                )

            # Before the digits there must be a dot `.`
            file_no_frame = file_no_ext.rstrip("1234567890")
            if not file_no_frame.endswith("."):
                cls.log.warning(
                    f"Output file '{first_file}' does not end with "
                    "`.{frame}.{extension}`."
                )
                return (
                    "Output file does not end with a dot separator before the "
                    "frame number."
                )

            if workfile_filename_no_ext not in first_file:
                return (
                    "Render output does not include workfile name: "
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

        # Repair all output filenames to ensure they end with `.{frame}.{ext}`
        base_path: str = output_node.base_path

        if is_multilayer:
            file_format = output_node.format.file_format
            ext = render_lib.get_file_format_extension(file_format)
            ext = f".{ext}"
            output_node.base_path = fix_filename(base_path, extension=ext)
        else:
            for file_slot in output_node.file_slots:
                if file_slot.use_node_format:
                    file_format = output_node.format.file_format
                else:
                    file_format = file_slot.format.file_format

                ext = render_lib.get_file_format_extension(file_format)
                ext = f".{ext}"
                file_slot.path = fix_filename(file_slot.path, extension=ext)

    @staticmethod
    def get_description():
        return inspect.cleandoc("""
        ### Compositor Output Filepaths Invalid
        
        The Output File node in the Compositor has invalid output paths.
        
        The filepaths must:
        
        - Include the workfile name in the output path, this is to ensure
          unique render paths for each workfile version.
          
        - End with `.####.{ext}`. It is allowed to specify no extension and
          frame tokens at all. As such, `filename.` is valid, because if frame
          number and extension are missing Blender will automatically append
          them.
        """)
