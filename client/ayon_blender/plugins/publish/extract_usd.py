import os

import bpy

from ayon_core.pipeline import KnownPublishError, OptionalPyblishPluginMixin
from ayon_blender.api import plugin, lib


class ExtractUSD(plugin.BlenderExtractor,
                 OptionalPyblishPluginMixin):
    """Extract as USD."""

    label = "Extract USD"
    hosts = ["blender"]
    families = ["usd"]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Ignore runtime instances (e.g. USD layers)
        # TODO: This is better done via more specific `families`
        if not instance.data.get("transientData", {}).get("instance_node"):
            return

        # Define extract output file path
        stagingdir = self.staging_dir(instance)
        filename = f"{instance.name}.usd"
        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.debug("Performing extraction..")

        # Select all members to "export selected"
        plugin.deselect_all()

        selected = []
        for obj in instance:
            if isinstance(obj, bpy.types.Object):
                obj.select_set(True)
                selected.append(obj)

        root = lib.get_highest_root(objects=instance[:])
        if not root:
            instance_node = instance.data["transientData"]["instance_node"]
            raise KnownPublishError(
                f"No root object found in instance: {instance_node.name}"
            )
        self.log.debug(f"Exporting using active root: {root.name}")

        context = plugin.create_blender_context(
            active=root, selected=selected)

        # Export USD
        with bpy.context.temp_override(**context):
            bpy.ops.wm.usd_export(
                filepath=filepath,
                selected_objects_only=True,
                export_textures=False,
                relative_paths=False,
                export_animation=False,
                export_hair=False,
                export_uvmaps=True,
                # TODO: add for new version of Blender (4+?)
                # export_mesh_colors=True,
                export_normals=True,
                export_materials=True,
                use_instancing=True
            )

        plugin.deselect_all()

        # Add representation
        representation = {
            'name': 'usd',
            'ext': 'usd',
            'files': filename,
            "stagingDir": stagingdir,
        }
        instance.data.setdefault("representations", []).append(representation)
        self.log.debug("Extracted instance '%s' to: %s",
                       instance.name, representation)


class ExtractModelUSD(ExtractUSD):
    """Extract model as USD."""

    label = "Extract USD (Model)"
    hosts = ["blender"]
    families = ["model"]

    # Driven by settings
    optional = True
