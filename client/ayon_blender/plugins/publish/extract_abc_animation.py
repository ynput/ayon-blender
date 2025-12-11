import os

import bpy

from ayon_core.lib import BoolDef, EnumDef
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

    evaluation_mode: str = "RENDER"

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        attr_values = self.get_attr_values_from_data(instance.data)

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
                end=instance.data["frameEndHandle"],
                subdiv_schema=attr_values.get("subdiv_schema", False),
                evaluation_mode=attr_values.get("evaluation_mode",
                                                self.evaluation_mode),
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

    @classmethod
    def get_attribute_defs(cls):
        return [
            BoolDef(
                "subdiv_schema",
                label="Alembic Mesh Subdiv Schema",
                tooltip="Export Meshes using Alembic's subdivision schema.\n"
                        "Enabling this includes creases with the export but "
                        "excludes the mesh's normals.\n"
                        "Enabling this usually result in smaller file size "
                        "due to lack of normals.",
                default=False
            ),
            EnumDef(
                "evaluation_mode",
                label="Alembic Evaluation Mode",
                items=[
                    {"value": "RENDER", "label": "Render"},
                    {"value": "VIEWPORT", "label": "Viewport"},
                ],
                tooltip=(
                    "For Alembic export determines visibility of objects, "
                    "modifier settings, and other areas\nwhere there are "
                    "different settings for viewport and rendering."
                ),
                default=cls.evaluation_mode
            )
        ]
