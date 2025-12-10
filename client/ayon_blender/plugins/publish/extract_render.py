import contextlib

import bpy
import pyblish.api

from ayon_blender.api import plugin


@contextlib.contextmanager
def render_range(frame_start, frame_end, step=1):
    """Context manager to temporarily set render frame range."""
    scene = bpy.context.scene
    original_start = scene.frame_start
    original_end = scene.frame_end
    original_step = scene.frame_step
    try:
        scene.frame_start = frame_start
        scene.frame_end = frame_end
        scene.frame_step = step
        yield
    finally:
        scene.frame_start = original_start
        scene.frame_end = original_end
        scene.frame_step = original_step


class ExtractLocalRender(
    plugin.BlenderExtractor
):
    """Render the sequence locally during publish when not using farm.

    This extractor renders the current scene's animation to the file output
    paths collected on the render instance. It only runs when the instance
    is not marked for farm processing (farm=False).
    """

    label = "Extract Local Render"
    hosts = ["blender"]
    families = ["render"]
    # Run after scene save but before other extractors
    order = pyblish.api.ExtractorOrder - 0.4

    def process(self, instance):
        # Skip if explicitly marked for farm
        if instance.data.get("farm"):
            self.log.debug("Instance marked for farm, skipping local render.")
            return

        frame_start: int = instance.data["frameStartHandle"]
        frame_end: int = instance.data["frameEndHandle"]
        step: int = int(instance.data.get("step", 1))

        # Ensure overwrite to avoid stopping on existing files
        bpy.context.scene.render.use_overwrite = True

        self.log.info("Rendering animation locally...")
        with render_range(frame_start, frame_end, step=step):
            bpy.ops.render.render(
                animation=True,
                write_still=False,
                # TODO: These arguments are only supported in Blender 5.0+
                #  so once we drop older releases we can potentially avoid
                #  the render range context manager
                # frame_start=frame_start,
                # frame_end=frame_end,
            )
        self.log.info("Local render finished.")
