import os
import pyblish.api
from ayon_blender.api import plugin
import bpy


class CollectTemporaryFilesCleanUp(plugin.BlenderInstancePlugin):
    """Collect Scene Render Temporary Files for the later clean up."""

    label = "Collect Scene Render Temporary Files"
    order = pyblish.api.CollectorOrder - 0.1
    hosts = ["blender"]
    targets = ["farm"]

def process(self, instance):
    temp_dir = bpy.context.scene.render.filepath
    if not os.path.exists(temp_dir):
        self.log.debug(f"Temporary directory does not exist: {temp_dir}")
        return
    self.log.debug(f"Collecting files for cleanup in directory: {temp_dir}")
    for file in os.listdir(temp_dir):
        file_path = os.path.join(temp_dir, file)
        if os.path.isfile(file_path):
            self.log.debug(f"Adding file to cleanup: {file_path}")
            instance.context.data["cleanupFullPaths"].append(file_path)
    instance.context.data["cleanupEmptyDirs"].append(temp_dir)
