import os
import itertools

from ayon_core.pipeline.publish import (
    PublishValidationError,
    ValidateContentsOrder,
)
from ayon_blender.api import plugin
import clique


class ValidateRenderLocalHasExistingFrames(plugin.BlenderInstancePlugin):
    """Validate all files for the representations exist on disk."""

    order = ValidateContentsOrder
    families = ["render.local_no_render"]
    label = "Validate Existing Frames"

    def process(self, instance):
        missing_paths = []
        for repre in instance.data.get("representations", []):
            files = repre.get("files")
            if isinstance(files, str):
                files = [files]

            staging_dir = repre["stagingDir"]
            for fname in files:
                path = os.path.join(staging_dir, fname)
                if not os.path.exists(path):
                    missing_paths.append(path)

        if missing_paths:
            collections, remainder = clique.assemble(missing_paths)
            for path in itertools.chain(collections, remainder):
                self.log.warning(f"Missing files: {path}")

            raise PublishValidationError(
                title="Missing existing frames",
                message=(
                    "Render has missing files. Please make sure to render the "
                    "missing frames or pick another render target."
                )
            )
