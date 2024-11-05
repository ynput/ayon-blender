import os
import re

import bpy
import pyblish.api

from ayon_blender.api import colorspace, plugin


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

        expected_files = {}
        output_paths = self.get_expected_outputs(comp_output_node)
        is_multilayer = self.is_multilayer_exr(comp_output_node)

        for output_path in output_paths:
            if is_multilayer:
                # Only ever a single output - we enforce the identifier to an
                # empty string to have it considered to not split into a
                # subname for the product
                aov_identifier = ""
            else:
                aov_identifier = self.get_aov_identifier(output_path)

            expected_files[aov_identifier] = self.generate_expected_frames(
                output_path,
                frame_start,
                frame_end,
                frame_step
            )

        context = instance.context
        instance.data.update({
            "families": ["render", "render.farm"],
            "fps": context.data["fps"],
            "byFrameStep": frame_step,
            "review": instance.data.get("review", False),
            "multipartExr": is_multilayer,
            "farm": True,
            "expectedFiles": [expected_files],
            "renderProducts": colorspace.ARenderProduct(
                frame_start=frame_start,
                frame_end=frame_end
            ),
        })

        colorspace_data = self.get_colorspace_data(comp_output_node)
        self.log.debug(f"Collected colorspace data: {colorspace_data}")
        instance.data.update(colorspace_data)

    def get_colorspace_data(
        self,
        node: "bpy.types.CompositorNodeOutputFile"
    ) -> dict:
        # OCIO not currently implemented in Blender, but the following
        # settings are required by the schema, so it is hardcoded.
        ocio_path = os.getenv("OCIO")
        if not ocio_path:
            # assume not color-managed, return fallback placeholder data
            return {
                "colorspaceConfig": "",
                "colorspaceDisplay": "sRGB",
                "colorspaceView": "ACES 1.0 SDR-video",
            }

        # Get from node or scene
        if node.format.color_management == "OVERRIDE":
            display: str = node.display_settings.display_device
            view: str = node.view_settings.view_transform
            # look: str = node.view_settings.look
        else:
            display: str = bpy.context.scene.display_settings.display_device
            view: str = bpy.context.scene.view_settings.view_transform
            # look: str = bpy.context.scene.view_settings.look

        return {
            "colorspaceConfig": ocio_path,
            "colorspaceDisplay": display,
            "colorspaceView": view,
        }

    def is_multilayer_exr(
        self,
        node: "bpy.types.CompositorNodeOutputFile"
    ) -> bool:
        return node.format.file_format == "OPEN_EXR_MULTILAYER"

    def get_expected_outputs(
        self,
        node: "bpy.types.CompositorNodeOutputFile"
    ):
        """Return the expected output files from a compositor node output file.

        The output paths are **not** converted to individual frames and will
        still contain the `####` frame padding tokens to. So the final path
        would still need to be constructed from the resulting path.

        Returns:
            list[str]: The full output image or sequence paths.

        """
        outputs: "list[str]" = []
        base_path: str = node.base_path

        if self.is_multilayer_exr(node):
            # Single multi-layered EXR containing all the images as layers
            # TODO: Collect the format and layer names contained inside
            #  the output
            # for layer_slot in node.layer_slots:
            #     name = layer_slot.name
            outputs.append(base_path)
        else:
            for file_slot in node.file_slots:
                # TODO: Should we skip file slots that are not connected?
                #  (what does blender do?)
                # TODO: Do we need to check `file_slot.save_as_render`?
                # TODO: Collect format from File Slot (it can override it)
                #  however this would also need support by other publish
                #  plug-ins to allow custom colorspace data per output AOV
                #  (render product) within a single instance
                # if file_slot.use_node_format:
                #     output_format = file_slot.format

                # Get full path
                sub_path: str = file_slot.path
                file_path = os.path.join(base_path, sub_path)
                outputs.append(file_path)

        return outputs

    @staticmethod
    def generate_expected_frames(
        path_with_frame_token: str,
        frame_start: int,
        frame_end: int,
        frame_step: int
    ):
        """Generate the expected files for each frame.

        It replaces the sequence of `#` with the frame number.

        Returns:
            list[str]: All frames for input path.

        """
        path = os.path.dirname(path_with_frame_token)
        file = os.path.basename(path_with_frame_token)
        file, ext = os.path.splitext(file)

        # TODO: What does blender do by default if the path does not include
        #  the `#` token in the name?
        expected_files = []
        for frame in range(frame_start, frame_end + 1, frame_step):
            # TODO: Compute padding from the path instead of assuming 4
            frame_str = str(frame).rjust(4, "0")
            filename = re.sub("#+", frame_str, file)
            expected_file = f"{os.path.join(path, filename)}.{ext}"
            expected_files.append(expected_file.replace("\\", "/"))

        return expected_files

    def get_aov_identifier(self, path: str) -> str:
        # TODO: Define sensible way to compute AOV name for the publish product
        #  based on the image outputs the comp node (when NOT multilayer EXR).
        #  This identifier will be the suffix for the product, like:
        #  `renderLightingMain.{aov}` -> `renderLightingMain.beauty`

        # Change "/path/to/my_filename.####.exr" to "my_filename"
        aov_identifier = os.path.basename(path).split("#", 1)[0].strip("._")
        self.log.info(f"AOV '{aov_identifier}' from filepath: {path}")
        return aov_identifier
