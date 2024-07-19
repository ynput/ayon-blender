from pathlib import Path

from pyblish.api import CollectorOrder
from ayon_blender.api import plugin


class CollectWorkfile(plugin.BlenderInstancePlugin):
    """Inject workfile data into its instance."""

    order = CollectorOrder
    label = "Collect Workfile"
    hosts = ["blender"]
    families = ["workfile"]

    def process(self, instance):
        """Process collector."""

        context = instance.context
        filepath = context.data.get("currentFile")
        if not filepath:
            self.log.warning("Deactivating workfile instance because no "
                             "current filepath is found. Please save your "
                             "workfile.")
            instance.data["publish"] = False
            return

        filepath = Path(filepath)
        ext = filepath.suffix

        instance.data.update(
            {
                "setMembers": [filepath.as_posix()],
                "frameStart": context.data.get("frameStart", 1),
                "frameEnd": context.data.get("frameEnd", 1),
                "handleStart": context.data.get("handleStart", 1),
                "handledEnd": context.data.get("handleEnd", 1),
                "representations": [
                    {
                        "name": ext.lstrip("."),
                        "ext": ext.lstrip("."),
                        "files": filepath.name,
                        "stagingDir": filepath.parent,
                    }
                ],
            }
        )
