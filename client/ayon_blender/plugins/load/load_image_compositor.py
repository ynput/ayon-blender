import os
from typing import Dict, List, Optional

import bpy

from ayon_core.lib.transcoding import VIDEO_EXTENSIONS
from ayon_blender.api import plugin, lib
from ayon_blender.api.pipeline import AVALON_CONTAINER_ID


class LoadImageCompositor(plugin.BlenderLoader):
    """Load media to the compositor."""

    product_types = {"render", "image", "plate"}
    representations = {"*"}

    label = "Load in Compositor"
    icon = "code-fork"
    color = "orange"

    def process_asset(
        self, context: dict, name: str, namespace: Optional[str] = None,
        options: Optional[Dict] = None
    ) -> Optional[List]:
        """
        Arguments:
            name: Use pre-defined name
            namespace: Use pre-defined namespace
            context: Full parenthood of representation to load
            options: Additional settings dictionary
        """
        path = self.filepath_from_context(context)

        # Enable nodes to ensure they can be loaded
        if not bpy.context.scene.use_nodes:
            self.log.info("Enabling 'use nodes' for Compositor")
            bpy.context.scene.use_nodes = True

        # Load the image in data
        image = bpy.data.images.load(path, check_existing=True)

        # Get the current scene's compositor node tree
        node_tree = bpy.context.scene.node_tree

        # Create a new image node
        img_comp_node = node_tree.nodes.new(type='CompositorNodeImage')
        img_comp_node.image = image
        self.set_source_and_colorspace(context, img_comp_node)

        data = {
            "schema": "openpype:container-2.0",
            "id": AVALON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
        }
        lib.imprint(img_comp_node, data)

        return [img_comp_node]

    def exec_remove(self, container: Dict) -> bool:
        """Remove the image comp node"""
        img_comp_node = container["node"]
        image: Optional[bpy.types.Image] = img_comp_node.image

        # Delete the compositor node
        bpy.context.scene.node_tree.nodes.remove(img_comp_node)

        # Delete the image if it remains unused
        self.remove_image_if_unused(image)

        return True

    def exec_update(self, container: Dict, context: Dict):
        """Update the image comp node to new context version."""
        path = self.filepath_from_context(context)
        img_comp_node = container["node"]

        old_image: Optional[bpy.types.Image] = img_comp_node.image

        new_image = bpy.data.images.load(path, check_existing=True)
        img_comp_node.image = new_image

        self.set_source_and_colorspace(context, img_comp_node)
        self.remove_image_if_unused(old_image)

        # Update representation id
        lib.imprint(img_comp_node, {
            "representation": context["representation"]["id"]
        })

    def set_source_and_colorspace(
        self,
        context: dict,
        image_comp_node: bpy.types.CompositorNodeImage
    ):
        """
        Set the image source (e.g. SEQUENCE or FILE), set the duration for
        a sequence and set colorspace if representation has colorspace data.
        """

        image = image_comp_node.image
        representation: dict = context["representation"]

        # Set image source
        source = "FILE"  # Single image file
        if representation["context"].get("udim"):
            source = "UDIM"
        elif representation["context"].get("frame"):
            source = "SEQUENCE"
        else:
            ext = os.path.splitext(image.filepath)[-1]
            if ext in VIDEO_EXTENSIONS:
                source = "MOVIE"

        image.source = source

        # Set duration on the compositor node if sequence is used
        if source in {"SEQUENCE", "MOVIE"}:
            version_attrib: dict = context["version"]["attrib"]
            frame_start = version_attrib.get("frameStart", 0)
            frame_end = version_attrib.get("frameEnd", 0)
            handle_start = version_attrib.get("handleStart", 0)
            handle_end = version_attrib.get("handleEnd", 0)
            frame_start_handle = frame_start - handle_start
            frame_end_handle = frame_end + handle_end
            duration: int = frame_end_handle - frame_start_handle + 1
            image_comp_node.frame_duration = duration
            if source == "SEQUENCE":
                image_comp_node.frame_start = frame_start_handle
                image_comp_node.frame_offset = frame_start_handle - 1
            else:
                image_comp_node.frame_start = frame_start_handle
                image_comp_node.frame_offset = 0

        # Set colorspace if representation has colorspace data
        if representation.get("colorspaceData"):
            colorspace: str = representation["colorspaceData"]["colorspace"]
            if colorspace:
                image.colorspace_settings.name = colorspace

    def remove_image_if_unused(self, image: bpy.types.Image):
        if image and not image.users:
            self.log.debug("Removing unused image: %s", image.name)
            bpy.data.images.remove(image)

    def switch(self, container, context):
        # Support switch in scene inventory
        self.update(container, context)
