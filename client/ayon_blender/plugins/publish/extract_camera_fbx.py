import os

import bpy

from ayon_core.pipeline import publish
from ayon_blender.api import plugin, lib


class ExtractCamera(
    plugin.BlenderExtractor, publish.OptionalPyblishPluginMixin
):
    """Extract as the camera as FBX."""

    label = "Extract Camera (FBX)"
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
        filename = f"{instance_name}.fbx"
        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.debug("Performing extraction..")

        plugin.deselect_all()

        selected = []

        camera = None

        for obj in instance:
            if obj.type == "CAMERA":
                obj.select_set(True)
                selected.append(obj)
                camera = obj
                break

        assert camera, "No camera found"

        context = plugin.create_blender_context(
            active=camera, selected=selected)

        scene_overrides = {
            "frame_start": instance.data.get("frameStart"),
            "frame_end": instance.data.get("frameEnd"),
            "frame_step": instance.data.get("frameStep"),
            "render.fps": instance.data.get("fps")
        }
        # Skip None value overrides
        scene_overrides = {
            key: value for key, value in scene_overrides.items()
            if value is not None
        }
        if "render.fps" in scene_overrides:
            scene_overrides["render.fps_base"] = 1

        with lib.attribute_overrides(bpy.context.scene, scene_overrides):
            with bpy.context.temp_override(**context):
                # We export the fbx
                bpy.ops.export_scene.fbx(
                    filepath=filepath,
                    use_active_collection=False,
                    use_selection=True,
                    bake_anim_use_nla_strips=False,
                    bake_anim_use_all_actions=False,
                    add_leaf_bones=False,
                    armature_nodetype='ROOT',
                    object_types={'CAMERA'},
                    bake_anim_simplify_factor=0.0
                )

        plugin.deselect_all()

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

