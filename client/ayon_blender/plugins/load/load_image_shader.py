from typing import Dict, List, Optional

from qtpy import QtWidgets
import bpy

from ayon_core.tools.utils import host_tools
from ayon_core.lib import EnumDef
from ayon_blender.api import plugin, lib
from ayon_core.pipeline import AYON_CONTAINER_ID


class LoadImageShaderEditor(plugin.BlenderLoader):
    """Load a product to the Shader Editor for selected mesh in Blender."""

    product_types = {"render", "image", "plate"}
    representations = {"*"}

    label = "Load to Shader Editor"
    icon = "code-fork"
    color = "orange"

    CREATE_NEW = "create_new"

    @classmethod
    def get_options(cls, contexts):

        selected_object = cls.get_selected_object()
        if not selected_object:
            return []

        slot_materials = [
            (i, material) for i, material
            in enumerate(selected_object.data.materials)
            # Ignore empty material slots
            if material is not None
        ]
        items = [
            {"value": i, "label": material.name}
            for i, material in slot_materials
        ]
        items.append(
            {"value": cls.CREATE_NEW, "label": "New Material"}
        )
        return [
            EnumDef(
                "material_slot",
                label="Material Slot",
                items=items,
                default=items[0]["value"]
            )
        ]

    @staticmethod
    def get_selected_object():
        selected_objects = lib.get_selection()
        for obj in selected_objects:
            if obj.type in {'MESH', 'SURFACE'}:
                return obj

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

        # In the current objects selection, I get the first one that is a
        # MESH or a SURFACE.
        # TODO: We tend to avoid acting on 'user selection' so that the loaders
        #  can run completely automatically, without user interaction or popups
        #  So we may want to investigate different approaches to this.
        cur_obj = self.get_selected_object()
        if cur_obj is None:
            self.log.info(
                "Load in Shader Editor: The process (image load) was "
                "cancelled, because no object (mesh or surface) was selected "
                "in Blender.")
            self.display_warning(
                "You did not select any object in Blender.\n"
                "So this process is cancelled.")
            return []

        # If the currently selected object has one or more materials, let's use
        # the first one. If it has no material, let's create a new one.
        material_slot = options.get("material_slot")
        if material_slot is None:
            # Get first slot with a material
            material_slot = next(
                (
                    i for i, material in enumerate(cur_obj.data.materials)
                    # Ignore empty material slots
                    if material is not None
                ), None
            )
        if material_slot is None or material_slot == self.CREATE_NEW:
            # Create a new material
            current_material = bpy.data.materials.new(name="material")
            current_material.use_nodes = True
            cur_obj.data.materials.append(current_material)
        else:
            current_material = cur_obj.data.materials[material_slot]
            current_material.use_nodes = True

        nodes = current_material.node_tree.nodes

        # Create an "Image Texture" node. It will appear in the Shader Editor
        # (which appears when you are in the "Shading" workspace tab), when you
        # select the "Object" filter (among this choice: Object, World,
        # Line Style).
        image_texture_node = nodes.new(type='ShaderNodeTexImage')

        # Load the image in data
        path = self.filepath_from_context(context)
        image = bpy.data.images.load(path)
        image_texture_node.image = image

        self.set_colorspace(context, image_texture_node)

        data = {
            "schema": "ayon:container-3.0",
            "id": AYON_CONTAINER_ID,
            "name": name,
            "namespace": namespace or '',
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
        }
        lib.imprint(image_texture_node, data)

        return [image_texture_node]

    def exec_remove(self, container: Dict) -> bool:
        """Remove the Image Texture node."""

        image_texture_node: bpy.types.ShaderNodeTexImage = container["node"]
        image: Optional[bpy.types.Image] = image_texture_node.image

        # Delete the node
        image_texture_node.id_data.nodes.remove(image_texture_node)

        # Delete the image if it remains unused
        self.remove_image_if_unused(image)

        return True

    def exec_update(self, container: Dict, context: Dict):
        """Update the Image Texture node to new context version."""

        path = self.filepath_from_context(context)
        image_texture_node: bpy.types.ShaderNodeTexImage = container["node"]

        old_image: Optional[bpy.types.Image] = image_texture_node.image

        new_image = bpy.data.images.load(path)
        image_texture_node.image = new_image

        self.set_colorspace(context, image_texture_node)
        self.remove_image_if_unused(old_image)

        # Update representation id
        lib.imprint(image_texture_node, {
            "representation": context["representation"]["id"]
        })

    def set_colorspace(
            self,
            context: dict,
            image_texture_node: bpy.types.ShaderNodeTexImage
    ):
        """
        Set colorspace if representation has colorspace data.
        """

        image = image_texture_node.image
        representation: dict = context["representation"]

        colorspace_data = representation.get("data", {}).get(
            "colorspaceData", {})
        if colorspace_data:
            colorspace: str = colorspace_data["colorspace"]
            if colorspace:
                image.colorspace_settings.name = colorspace

    def remove_image_if_unused(self, image: bpy.types.Image):
        if image and not image.users:
            self.log.debug("Removing unused image: %s", image.name)
            bpy.data.images.remove(image)

    def display_warning(self, message):
        loader_gui_window = host_tools.get_tool_by_name("loader")

        QtWidgets.QMessageBox.warning(
            loader_gui_window,
            "Warning",
            message,
            buttons=QtWidgets.QMessageBox.Ok,
            defaultButton=QtWidgets.QMessageBox.Ok)
