import os

import bpy

from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_blender.api import plugin
from ayon_blender.api.render_lib import prepare_rendering


class ValidateDeadlinePublish(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Validates Render File Directory is
    not the same in every submission
    """

    order = ValidateContentsOrder
    families = ["render"]
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
        tree = bpy.context.scene.node_tree
        output_type = "CompositorNodeOutputFile"
        output_node = None
        # Remove all output nodes that include "AYON" in the name.
        # There should be only one.
        for node in tree.nodes:
            if node.bl_idname == output_type and "AYON" in node.name:
                output_node = node
                break
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
        prepare_rendering(container)
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
        bpy.context.scene.render.filepath = "/tmp/"
        cls.log.debug("Reset the render output folder...")
