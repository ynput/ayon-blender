import os

import bpy
from pathlib import Path

from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_blender.api import plugin
from ayon_blender.api.render_lib import update_render_product


def get_composite_output_node():
    """Get composite output node for validation

    Returns:
        node: composite output node
    """
    tree = bpy.context.scene.node_tree
    output_type = "CompositorNodeOutputFile"
    output_node = None
    # Remove all output nodes that include "AYON" in the name.
    # There should be only one.
    for node in tree.nodes:
        if node.bl_idname == output_type and "AYON" in node.name:
            output_node = node
            break
    return output_node


class ValidateDeadlinePublish(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Validates Render File Directory is
    not the same in every submission
    """

    order = ValidateContentsOrder
    families = ["renderlayer"]
    hosts = ["blender"]
    label = "Validate Render Output for Deadline"
    optional = True
    actions = [RepairAction]

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
        output_node = get_composite_output_node()
        if not output_node:
            msg = "No output node found in the compositor tree."
            invalid.append(msg)

        filepath = bpy.data.filepath
        file = os.path.basename(filepath)
        filename, ext = os.path.splitext(file)
        if filename not in output_node.base_path:
            msg = (
                "Render output folder doesn't match the blender scene name! "
                "Use Repair action to fix the folder file path."
            )
            invalid.append(msg)
        if not bpy.context.scene.render.filepath:
            msg = (
                "No render filepath set in the scene!"
                "Use Repair action to fix the render filepath."
            )
            invalid.append(msg)
        return invalid

    @classmethod
    def repair(cls, instance):
        container = instance.data["transientData"]["instance_node"]
        output_node = get_composite_output_node()
        render_data = container.get("render_data")
        is_multilayer = render_data.get("multilayer_exr")
        filename = os.path.basename(bpy.data.filepath)
        filename = os.path.splitext(filename)[0]
        if is_multilayer:
            render_folder = render_data.get("render_folder")
            aov_sep = render_data.get("aov_separator")
            output_dir = os.path.dirname(bpy.data.filepath)
            output_dir = os.path.join(output_dir, render_folder, filename)
            output_node.base_path = f"{output_dir}_{output_node.layer}{aov_sep}beauty.####"
            new_output_dir = os.path.dirname(output_node.base_path)
        else:
            output_node_dir = os.path.dirname(output_node.base_path)
            new_output_dir = os.path.join(output_node_dir, filename)
            output_node.base_path = new_output_dir

        new_output_dir = Path(new_output_dir)
        render_product = render_data.get("render_product")
        aov_file_product = render_data.get("aov_file_product")
        updated_render_product = update_render_product(
            container.name, new_output_dir, render_product)
        render_data["render_product"] = updated_render_product
        if aov_file_product:
            updated_aov_file_product = update_render_product(
                container.name, new_output_dir, aov_file_product)
            render_data["aov_file_product"] = updated_aov_file_product

        tmp_render_path = os.path.join(os.getenv("AYON_WORKDIR"), "renders", "tmp")
        tmp_render_path = tmp_render_path.replace("\\", "/")
        os.makedirs(tmp_render_path, exist_ok=True)
        bpy.context.scene.render.filepath = f"{tmp_render_path}/"

        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
