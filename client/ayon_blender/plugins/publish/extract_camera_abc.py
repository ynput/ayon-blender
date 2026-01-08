import os

import bpy

from ayon_core.pipeline import publish
from ayon_blender.api import plugin, lib


class ExtractCameraABC(
    plugin.BlenderExtractor, publish.OptionalPyblishPluginMixin
):
    """Extract camera as ABC."""

    label = "Extract Camera (ABC)"
    hosts = ["blender"]
    families = ["camera"]
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

        instance_node = instance.data["transientData"]["instance_node"]
        if isinstance(instance_node, bpy.types.Collection):
            members = list(instance)
            active = lib.get_highest_root(members)
            selected = members
        elif isinstance(instance_node, bpy.types.Object):
            # Legacy behavior where camera instances were asset groups
            asset_group = instance_node
            # Need to cast to list because children is a tuple
            selected = list(asset_group.children)
            active = selected[0]
        else:
            raise TypeError(
                "Instance node is of wrong type, expecting object or "
                f"collection but got: {instance_node}"
            )

        for obj in selected:
            if isinstance(obj, bpy.types.Object):
                obj.select_set(True)

        context = plugin.create_blender_context(
            active=active, selected=selected)

        scene_overrides = {
            "unit_settings.scale_length": instance.data.get("unitScale"),
        }
        # Skip None value overrides
        scene_overrides = {
            key: value for key, value in scene_overrides.items()
            if value is not None
        }

        with lib.attribute_overrides(bpy.context.scene, scene_overrides):
            with bpy.context.temp_override(**context):
                # We export the abc
                bpy.ops.wm.alembic_export(
                    filepath=filepath,
                    selected=True,
                    flatten=True,
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
