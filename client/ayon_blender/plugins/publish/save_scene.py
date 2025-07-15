import pyblish.api

from ayon_core.pipeline import registered_host, KnownPublishError


class SaveCurrentSceneBlender(pyblish.api.ContextPlugin):
    """Save current scene.

    Always ensure the current scene is saved before we continue extracting,
    so that our scene state is reproducable and consistent.
    """

    label = "Save current file"
    order = pyblish.api.ExtractorOrder - 0.49
    hosts = ["blender"]

    def process(self, context):
        host = registered_host()

        # If file has no modifications, skip forcing a file save
        # TODO: Making changes to the scene through Python does not mark the
        #  scene as modified, so we cannot rely on this.
        # if not host.workfile_has_unsaved_changes():
        #     self.log.debug("Skipping file save as there "
        #                    "are no unsaved changes..")
        #     return

        # Filename must not have changed since collecting
        current_file = host.get_current_workfile()
        if context.data["currentFile"] != current_file:
            raise KnownPublishError(
                "Collected filename mismatches from current scene name."
            )

        self.log.debug(f"Saving current file: {current_file}")
        host.save_workfile()
