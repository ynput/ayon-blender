from __future__ import annotations
import os
import re
from typing import TypedDict, Optional

import pyblish.api
import clique

import bpy

from ayon_blender.api import colorspace, plugin, render_lib


def files_as_sequence(files) -> list[str]:
    """Convert sequence of files to sequence pattern.

    Convert a list of files to a sequence pattern purely used for improved
    human-readable logging purposes."""
    # clique.PATTERNS["frames"] but also allow `_` before digits
    pattern = r"(?P<index>(?P<padding>0*)\d+)\.\D+\d?$"
    files = [os.path.basename(f) for f in files]
    collections, remainder = clique.assemble(
        files,
        patterns=[pattern],
        assume_padded_when_ambiguous=True,
    )
    names = [str(collection) for collection in collections]
    names.extend(remainder)
    return names


class RenderColorspaceData(TypedDict):
    """Colorspace data for the render instance.

    This is used to store the colorspace configuration for the render output.
    It includes the OCIO configuration, display, and view settings.

    Attributes:
        colorspaceConfig (str): Path to the OCIO configuration file.
        colorspaceDisplay (str): Display device name.
        colorspaceView (str): View transform name.
        colorspace (str): Colorspace of the output image.
    """
    colorspaceConfig: str
    colorspaceDisplay: str
    colorspaceView: str
    colorspace: str


class CollectBlenderRender(plugin.BlenderInstancePlugin):
    """Gather all publishable render instances.

    For the instance node (bpy.types.CompositorNodeOutputFile) we collect the
    configured output paths (FileSlots or LayerSlots) and their colorspaces.

    ### AOV identifiers

    When multiple outputs are present (only the case when not rendering to
    multilayer EXR) then we assign each output an 'aov identifier' that will
    be added to the product name. So that product: `renderLightingMain` becomes
    for example `renderLightingMain.beauty` and `renderLightingMain.diffuse`.

    ### Requires enabled compositing node tree

    The render workflow requires Blender to be configured to use the
    Compositor Node Tree, because it relies on `CompositorNodeOutputFile` to
    define the output files for rendering.

    """

    order = pyblish.api.CollectorOrder + 0.01
    hosts = ["blender"]
    families = ["render"]
    label = "Collect Render"
    sync_workfile_version = False

    def process(self, instance: pyblish.api.Instance):

        comp_output_node: "bpy.types.CompositorNodeOutputFile" = (
            instance.data["transientData"]["instance_node"])
        frame_start: int = instance.data["frameStartHandle"]
        frame_end: int = instance.data["frameEndHandle"]
        frame_step: int = instance.data["creator_attributes"].get("step", 1)
        review: bool = instance.data["creator_attributes"].get("review", False)

        expected_files: dict[str, list[str]] = {}
        output_paths = self.get_expected_outputs(comp_output_node)
        is_multilayer = self.is_multilayer_exr(comp_output_node)

        colorspace_data = self.get_colorspace_data(comp_output_node)
        self.log.debug(f"Collected colorspace data: {colorspace_data}")
        if colorspace_data:
            instance.data.update(colorspace_data)

        render_products = colorspace.ARenderProduct(
            frame_start=frame_start,
            frame_end=frame_end
        )

        for output_path in output_paths:
            if is_multilayer:
                # Only ever a single output - we enforce the identifier to an
                # empty string to have it considered to not split into a
                # subname for the product
                aov_identifier = ""
            else:
                aov_identifier = self.get_aov_identifier(
                    output_path,
                    instance
                )

            aov_label: str = aov_identifier or "<beauty>"
            self.log.debug(
                f"Expecting outputs for AOV {aov_label}: "
                f"{output_path}"
            )

            expected_files[aov_identifier] = self.generate_expected_frames(
                output_path,
                frame_start,
                frame_end,
                frame_step
            )

            # We need to have a matching 'renderProduct' entry so that
            # the logic in core for `_create_instances_for_aov` assigns
            # the colorspace data to the relevant AOV instance.
            aov_colorspace: str = (
                colorspace_data["colorspace"] if colorspace_data else ""
            )
            render_products.add_render_product(
                product_name=aov_identifier,
                colorspace=aov_colorspace
            )

            # Log the expected sequence of frames for the AOV
            files = files_as_sequence(expected_files[aov_identifier])
            self.log.debug(f"Expected frames: {files}")

        creator_attribute = instance.data["creator_attributes"]

        # Collect Render Target
        local_render: bool = creator_attribute.get("render_target") == "local"

        context = instance.context
        instance.data.update({
            "families": ["render", "render.farm"],
            "fps": context.data["fps"],
            "byFrameStep": frame_step,
            "review": review,
            "multipartExr": is_multilayer,
            "farm": not local_render,
            "expectedFiles": [expected_files],
            "renderProducts": render_products,
        })

    def get_colorspace_data(
        self,
        node: "bpy.types.CompositorNodeOutputFile"
    ) -> Optional[RenderColorspaceData]:
        ocio_path = os.getenv("OCIO")
        if not ocio_path:
            # Assume not color-managed
            return None

        # TODO: Technically Blender hides/disabled Display/View versus
        #  Colorspace depending on `node.format.has_linear_colorspace`
        #  which may mean it uses one of the two instead of both.
        # Get from node or scene
        if node.format.color_management == "OVERRIDE":
            display: str = node.format.display_settings.display_device
            view: str = node.format.view_settings.view_transform
            colorspace: str = node.format.linear_colorspace_settings.name
            # look: str = node.format.view_settings.look
        else:
            display: str = bpy.context.scene.display_settings.display_device
            view: str = bpy.context.scene.view_settings.view_transform
            # TODO: Where do we get colorspace if it doesn't come from node
            #  override nor scene override? In Blender 5+ there seems to be
            #  bpy.context.blend_data.colorspace.working_space but similar
            #  does not exist in Blender 4
            colorspace: str = "ACEScg"
            # look: str = bpy.context.scene.view_settings.look

        return {
            "colorspaceConfig": ocio_path,
            "colorspaceDisplay": display,
            "colorspaceView": view,
            "colorspace": colorspace
        }

    def is_multilayer_exr(
        self,
        node: "bpy.types.CompositorNodeOutputFile"
    ) -> bool:
        return node.format.file_format == "OPEN_EXR_MULTILAYER"

    def get_expected_outputs(
        self,
        node: "bpy.types.CompositorNodeOutputFile"
    ) -> list[str]:
        """Return the expected output files from a compositor node output file.

        The output paths are **not** converted to individual frames and will
        still contain the `####` frame padding tokens to. So the final path
        would still need to be constructed from the resulting path.

        Even if the path set in the scene does not contain the `#` frame
        tokens or an extension, this method will ensure that the returned
        paths do and qualify as a full path with `#` as padding frame tokens.

        Returns:
            list[str]: The full output image or sequence paths.

        """
        outputs: list[str] = []
        base_path: str = node.base_path

        if self.is_multilayer_exr(node):
            # Single multi-layered EXR containing all the images as layers
            # for layer_slot in node.layer_slots:
            #     name = layer_slot.name
            # Resolve the full render path for the output path
            file_path = self._resolve_full_render_path(
                path=base_path,
                file_format=node.format.file_format
            )
            outputs.append(file_path)
        else:
            for file_slot in node.file_slots:
                # TODO: Should we skip file slots that are not connected?
                #  (what does blender do?)
                # TODO: Do we need to check `file_slot.save_as_render`?
                # TODO: Collect format from File Slot (it can override it)
                #  however this would also need support by other publish
                #  plug-ins to allow custom colorspace data per output AOV
                #  (render product) within a single instance
                if file_slot.use_node_format:
                    output_format = node.format.file_format
                else:
                    output_format = file_slot.format.file_format

                # Append slot path to base path
                sub_path: str = file_slot.path
                file_path = os.path.join(base_path, sub_path)

                # Resolve the full render path for the output path
                file_path = self._resolve_full_render_path(
                    path=file_path,
                    file_format=output_format
                )

                outputs.append(file_path)

        return outputs

    def _resolve_full_render_path(
            self,
            path: str,
            file_format: str
    ) -> str:
        """Resolve the full render path for the output path.

        Filepaths in render outputs may be set relatively, with or
        without # tokens, with or without file extension. However, we need
        them consistently formatted for collecting them correctly.
        So we ensure the # token is present and the file extension is added.

        The output path will be a normalized, absolute path with `#` tokens
        in it that indicated the padded frame number.

        """
        # Ensure the extension is for the file
        extension = render_lib.get_file_format_extension(file_format)
        path = bpy.path.ensure_ext(path, f".{extension}")

        # If the path does not contain a frame token `#` then we append
        # the default frame token `####` to the end of the path before the
        # extension.
        if "#" not in os.path.basename(path):
            base, ext = os.path.splitext(path)
            path = f"{base}####{ext}"

        # Generate an absolute normalized path for the output
        path = bpy.path.abspath(path)
        path = os.path.normpath(path)
        return path

    @staticmethod
    def generate_expected_frames(
        path_with_frame_token: str,
        frame_start: int,
        frame_end: int,
        frame_step: int
    ) -> list[str]:
        """Generate the expected files for each frame.

        It replaces the sequence of `#` with the frame number.

        Returns:
            list[str]: All frames for input path.

        """
        directory, filename = os.path.split(path_with_frame_token)

        # Find the last occurrence of `#+` in the filename to determine
        # the frame token position. If multiple `%#` patterns are present
        # in the filename Blender uses the last one for the frame number.
        match = re.search(r"(#+)[^#]+$", filename)
        if not match:
            raise ValueError(
                f"Path '{path_with_frame_token}' does not contain a frame "
                "token '#'."
            )
        padding: int = len(match.group(1))
        filename, ext = os.path.splitext(filename)

        filename_head = filename[:match.start(1)]
        filename_tail = filename[match.end(1):]

        expected_files: list[str] = []
        for frame in range(frame_start, frame_end + 1, frame_step):
            # Replace #### with padded number
            frame_str = str(frame).zfill(padding)
            frame_filename = f"{filename_head}{frame_str}{filename_tail}"
            expected_file = f"{os.path.join(directory, frame_filename)}{ext}"
            expected_files.append(expected_file.replace("\\", "/"))

        return expected_files

    def get_aov_identifier(
            self, path: str,
            instance: pyblish.api.Instance
    ) -> str:
        # TODO: Define sensible way to compute AOV name for the publish product
        #  based on the image outputs the comp node (when NOT multilayer EXR).
        #  This identifier will be the suffix for the product, like:
        #  `renderLightingMain.{aov}` -> `renderLightingMain.beauty`
        # Change "/path/to/my_filename.####.exr" to "my_filename"
        aov_identifier = os.path.basename(path).split("#", 1)[0].strip("._")

        # The creator's prepare rendering setup logic will create the filenames
        # prefixed with `{variant}_`. We don't want to include that as a part
        # of the AOV identifier because it'd double the variant in the product
        # name.
        variant = instance.data.get("variant", "")
        variant_prefix = f"{variant}_"
        if aov_identifier.startswith(variant_prefix):
            self.log.debug(
                f"Stripping variant '{variant}' prefix from AOV identifier: "
                f"{aov_identifier}"
            )
            aov_identifier = aov_identifier.removeprefix(variant_prefix)

        self.log.debug(f"'{aov_identifier}' AOV from filepath: {path}")
        return aov_identifier
