import os
import glob

import pyblish.api
from ayon_blender.api import capture, plugin
from ayon_blender.api.lib import maintained_time, get_capture_preset

import bpy


class ExtractThumbnail(plugin.BlenderExtractor):
    """Extract viewport thumbnail.

    Takes review camera and creates a thumbnail based on viewport
    capture.

    """

    label = "Extract Thumbnail"
    hosts = ["blender"]
    families = ["review.playblast"]
    order = pyblish.api.ExtractorOrder + 0.01

    def process(self, instance):
        self.log.debug("Extracting capture..")

        if instance.data.get("thumbnailSource"):
            self.log.debug("Thumbnail source found, skipping...")
            return

        stagingdir = self.staging_dir(instance)
        folder_name = instance.data["folderEntity"]["name"]
        product_name = instance.data["productName"]
        filename = f"{folder_name}_{product_name}"

        path = os.path.join(stagingdir, filename)

        self.log.debug(f"Outputting images to {path}")

        camera = instance.data.get("review_camera", "AUTO")
        start = instance.data.get("frameStart", bpy.context.scene.frame_start)
        isolate = instance.data("isolate", None)

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
            "end_frame": start,
            "filename": path,
            "overwrite": True,
            "isolate": isolate,
            "log": self.log,
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
        extension = preset["image_settings"].get("file_format", "PNG").lower()
        with maintained_time():
            path = capture(**preset)

        thumbnail = os.path.basename(self._fix_output_path(path, extension))

        self.log.debug(f"thumbnail: {thumbnail}")

        instance.data.setdefault("representations", [])

        representation = {
            "name": "thumbnail",
            "ext": extension,
            "files": thumbnail,
            "stagingDir": stagingdir,
            "thumbnail": True
        }
        instance.data["representations"].append(representation)

    def _fix_output_path(self, filepath, extension):
        """Workaround to return correct filepath.

        To workaround this we just glob.glob() for any file extensions and
        assume the latest modified file is the correct file and return it.

        """
        # Catch cancelled playblast
        if filepath is None:
            self.log.warning(
                "Playblast did not result in output path. "
                "Playblast is probably interrupted."
            )
            return None

        if not os.path.exists(filepath):
            files = glob.glob(f"{filepath}.*.{extension}")

            if not files:
                raise RuntimeError(f"Couldn't find playblast from: {filepath}")
            filepath = max(files, key=os.path.getmtime)

        return filepath
