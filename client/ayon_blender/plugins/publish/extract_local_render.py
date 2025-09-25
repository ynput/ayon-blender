import os

import bpy
import pyblish.api

from ayon_core.pipeline import publish
from ayon_blender.api import plugin


class ExtractLocalRender(
    plugin.BlenderExtractor,
    publish.OptionalPyblishPluginMixin,
):
    """Render the sequence locally during publish when not using farm.

    This extractor renders the current scene's animation to the file output
    paths collected on the render instance. It only runs when the instance
    is not marked for farm processing (farm=False).
    """

    label = "Extract Local Render"
    hosts = ["blender"]
    families = ["render"]
    optional = True
    # Run after scene save but before other extractors
    order = pyblish.api.ExtractorOrder - 0.48

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Skip if explicitly marked for farm
        if instance.data.get("farm"):
            self.log.info("Instance marked farm=True; skipping local render.")
            return

        # Expected files were precomputed by the collector
        expected = instance.data.get("expectedFiles", [])
        expected = expected[0] if expected else {}

        # Ensure output directories exist
        for files in expected.values():
            if not files:
                continue
            dirpath = os.path.dirname(files[0])
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)

        # Ensure overwrite to avoid stopping on existing files
        bpy.context.scene.render.use_overwrite = True

        self.log.info("Rendering animation locally...")
        bpy.ops.render.render(animation=True, write_still=False)
        self.log.info("Local render finished.")

        # Register rendered files as representations
        representations = instance.data.setdefault("representations", [])
        for aov, files in expected.items():
            if not files:
                continue
            first = files[0]
            dirpath = os.path.dirname(first)
            ext = os.path.splitext(first)[1].lstrip(".").lower() or "exr"

            representations.append({
                "name": ext,
                "ext": ext,
                "files": [os.path.basename(f) for f in files],
                "stagingDir": dirpath,
            })

        self.log.debug(
            f"Added {len(expected)} representations for local render.")


