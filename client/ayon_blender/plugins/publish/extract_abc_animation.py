import os

import bpy

from ayon_core.pipeline import publish
from ayon_blender.api import plugin


class ExtractAnimationABC(
    plugin.BlenderExtractor,
    publish.OptionalPyblishPluginMixin,
):
    """Extract as ABC."""

    label = "Extract Animation ABC"
    hosts = ["blender"]
    families = ["animation"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Define extract output file path
        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        instance_name = f"{folder_name}_{product_name}"
        filename = f"{instance_name}.abc"

        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.debug("Performing extraction..")

        plugin.deselect_all()

        selected = []
        asset_group = instance.data["transientData"]["instance_node"]

        objects = []
        for obj in instance:
            if isinstance(obj, bpy.types.Collection):
                for child in obj.all_objects:
                    objects.append(child)
        for obj in objects:
            children = [o for o in bpy.data.objects if o.parent == obj]
            for child in children:
                objects.append(child)

        for obj in objects:
            obj.select_set(True)
            selected.append(obj)

        context = plugin.create_blender_context(
            active=asset_group, selected=selected)
        with bpy.context.temp_override(**context):
            # We export the abc
            bpy.ops.wm.alembic_export(
                filepath=filepath,
                selected=True,
                flatten=False,
                start=instance.data["frameStartHandle"],
                end=instance.data["frameEndHandle"]
            )

        plugin.deselect_all()

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'abc',
            'ext': 'abc',
            'files': filename,
            "stagingDir": stagingdir,
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extracted instance '%s' to: %s",
                       instance.name, representation)
