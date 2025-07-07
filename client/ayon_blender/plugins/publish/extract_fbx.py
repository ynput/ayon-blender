import os

import bpy

from ayon_core.pipeline import publish
from ayon_blender.api import plugin


class ExtractFBX(
    plugin.BlenderExtractor, publish.OptionalPyblishPluginMixin
):
    """Extract as FBX."""

    label = "Extract FBX"
    hosts = ["blender"]
    families = ["model", "rig"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Define extract output file path
        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        instance_name = f"{folder_name}_{product_name}"
        filename = f"{instance_name}.fbx"
        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.debug("Performing extraction..")

        plugin.deselect_all()

        asset_group = instance.data["transientData"]["instance_node"]

        selected = []
        for obj in instance:
            obj.select_set(True)
            selected.append(obj)

        context = plugin.create_blender_context(
            active=asset_group, selected=selected)

        new_materials = []
        new_materials_objs = []
        objects = list(asset_group.children)

        for obj in objects:
            objects.extend(obj.children)
            if obj.type == 'MESH' and len(obj.data.materials) == 0:
                mat = bpy.data.materials.new(obj.name)
                obj.data.materials.append(mat)
                new_materials.append(mat)
                new_materials_objs.append(obj)

        with bpy.context.temp_override(**context):
            # We export the fbx
            bpy.ops.export_scene.fbx(
                filepath=filepath,
                use_active_collection=False,
                use_selection=True,
                mesh_smooth_type='FACE',
                add_leaf_bones=False
            )

        plugin.deselect_all()

        for mat in new_materials:
            bpy.data.materials.remove(mat)

        for obj in new_materials_objs:
            obj.data.materials.pop()

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'fbx',
            'ext': 'fbx',
            'files': filename,
            "stagingDir": stagingdir,
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extracted instance '%s' to: %s",
                       instance.name, representation)


