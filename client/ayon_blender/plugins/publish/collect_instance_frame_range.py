import pyblish.api
from ayon_blender.api import plugin


class CollectFrameRangeFromCreator(plugin.BlenderInstancePlugin):

    order = pyblish.api.CollectorOrder - 0.4
    hosts = ["blender"]
    families = ["*"]
    label = "Collect Frame Range from creator"

    def process(self, instance):
        creator_attributes: dict = instance.data.get("creator_attributes", {})
        frame_keys = [
            "frameStart",
            "frameEnd",
            "handleStart",
            "handleEnd"
        ]
        for key in frame_keys:
            if key in creator_attributes:
                instance.data[key] = creator_attributes[key]

        if all(key in instance.data for key in frame_keys):
            # Calculate frameStartHandle and frameEndHandle
            instance.data["frameStartHandle"] = (
                instance.data["frameStart"] - instance.data["handleStart"]
            )
            instance.data["frameEndHandle"] = (
                instance.data["frameEnd"] - instance.data["handleEnd"]
            )
