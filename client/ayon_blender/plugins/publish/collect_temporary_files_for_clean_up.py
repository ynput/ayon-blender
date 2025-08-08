import os
import pyblish.api


class CollectTemporaryFilesForCleanUp(pyblish.api.InstancePlugin):
    """Compare rendered and expected files"""

    label = "Collect Temporary Files for Clean Up"
    order = pyblish.api.CollectorOrder - 0.1
    hosts = ["blender"]
    targets = ["farm"]

def process(self, instance):
    for repre in instance.data["representations"]:
        staging_dir = repre["stagingDir"]
        temp_dir = os.path.join(staging_dir, "tmp")
        if not os.path.exists(temp_dir):
            self.log.debug(f"Temporary directory does not exist: {temp_dir}")
            continue
        self.log.debug(f"Collecting files for cleanup in directory: {temp_dir}")
        for file in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, file)
            if os.path.isfile(file_path):
                self.log.debug(f"Adding file to cleanup: {file_path}")
                instance.context.data["cleanupFullPaths"].append(file_path)
        instance.context.data["cleanupEmptyDirs"].append(temp_dir)
