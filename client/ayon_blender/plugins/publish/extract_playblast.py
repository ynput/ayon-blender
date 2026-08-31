import os

import clique
import pyblish.api

import bpy

from ayon_core.pipeline import publish
from ayon_blender.api import capture, plugin
from ayon_blender.api.lib import maintained_time, get_capture_preset


class ExtractPlayblast(
    plugin.BlenderExtractor, publish.OptionalPyblishPluginMixin
):
    """
    Extract viewport playblast.

    Takes review camera and creates review Quicktime video based on viewport
    capture.
    """

    label = "Extract Playblast"
    hosts = ["blender"]
    families = ["review.playblast"]
    optional = True
    order = pyblish.api.ExtractorOrder + 0.01

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # get scene fps
        fps = instance.data.get("fps")
        if fps is None:
            fps = bpy.context.scene.render.fps
            instance.data["fps"] = fps

        self.log.debug(f"fps: {fps}")

        # If start and end frames cannot be determined,
        # get them from Blender timeline.
        start = instance.data.get("frameStart", bpy.context.scene.frame_start)
        end = instance.data.get("frameEnd", bpy.context.scene.frame_end)

        self.log.debug(f"start: {start}, end: {end}")
        assert end >= start, "Invalid time range!"

        # get cameras
        camera = instance.data.get("review_camera", None)

        # get isolate objects list
        isolate = instance.data.get("isolate", None)

        # get output path
        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        filename = f"{folder_name}_{product_name}"

        path = os.path.join(stagingdir, filename)

        self.log.debug(f"Outputting images to {path}")
        task_data = instance.data["anatomyData"].get("task", {})
        preset = get_capture_preset(
            task_data.get("name"),
            task_data.get("type"),
            instance.data["productName"],
            instance.context.data["project_settings"],
            log=self.log
        )
        # additional required parameters for playblast
        preset.update({
            "camera": camera,
            "start_frame": start,
            "end_frame": end,
            "filename": path,
            "overwrite": True,
            "isolate": isolate,
            "log": self.log
        })
        # This would be removed after the transition of
        # the new capture preset system.
        if not preset.get("image_settings"):
            preset.setdefault(
                "image_settings",
                {
                    "file_format": "PNG",
                    "color_mode": "RGB",
                    "color_depth": "8",
                    "compression": 15,
                },
            )

        with maintained_time():
            path = capture(**preset)

        self.log.debug(f"playblast path {path}")
        self._maintain_publisher_focus()

        collected_files = os.listdir(stagingdir)
        extension = preset["image_settings"].get("file_format", "PNG").lower()
        extension_pattern = "jpeg" if extension == "jpeg" else extension
        collections, _remainder = clique.assemble(
            collected_files,
            patterns=[
                f"{filename}\\.{clique.DIGITS_PATTERN}\\."
                f"{extension_pattern}$"
            ],
            minimum_items=1
        )

        if len(collections) > 1:
            raise RuntimeError(
                f"More than one collection found in stagingdir: {stagingdir}"
            )
        elif len(collections) == 0:
            raise RuntimeError(
                f"No collection found in stagingdir: {stagingdir}"
            )

        frame_collection = collections[0]

        self.log.debug(f"Found collection of interest {frame_collection}")

        # `instance.data["files"]` must be `str` if single frame
        files = list(frame_collection)
        extension = os.path.splitext(files[0])[1].lstrip(".").lower()
        if len(files) == 1:
            files = files[0]

        tags = ["review"]
        if not instance.data.get("keepImages"):
            tags.append("delete")

        representation = {
            "name": extension,
            "ext": extension,
            "files": files,
            "stagingDir": stagingdir,
            "frameStart": start,
            "frameEnd": end,
            "fps": fps,
            "tags": tags,
            "camera_name": camera
        }
        instance.data.setdefault("representations", []).append(representation)

    def _maintain_publisher_focus(self):
        """Restore publisher at the top widget by using bpy.app.timers."""
        def delayed_publisher_restore():
            """Delayed call to bring publisher window back to front."""
            # Double-check availability before calling
            if not hasattr(bpy.ops.wm, 'ayon_publisher'):
                return
            bpy.ops.wm.ayon_publisher()

        self.log.debug("Publisher focus restoration setup completed")
        bpy.app.timers.register(
            delayed_publisher_restore,
            first_interval=0.1
        )
