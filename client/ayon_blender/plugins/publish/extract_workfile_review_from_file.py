"""Attach an existing image/video file as review to the workfile publish.

Unlike ``ExtractPlayblast`` (which requires a review instance with a single
camera and renders the viewport), this plugin lets the artist attach an
already existing image or video file straight from disk as the review for the
*workfile* product.

A "Review file" file picker is added to the Workfile instance in the
publisher. When a file is picked, it is integrated as a ``review`` tagged
representation on the workfile product and a thumbnail is generated from it by
the core ``ExtractThumbnailFromSource`` plugin. Leaving the field empty is a
no-op, so existing workfile publishes are unaffected.
"""

import os
import shutil

import pyblish.api

from ayon_core.lib import FileDef
from ayon_core.pipeline import publish
from ayon_core.pipeline.publish import KnownPublishError

from ayon_blender.api import plugin


# Extensions offered by the file picker and used to decide how to treat the
# attached file. Keep them lowercase, with the leading dot.
VIDEO_EXTENSIONS = {
    ".mov", ".mp4", ".mkv", ".avi", ".m4v", ".webm", ".mxf", ".wmv",
}
IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".gif",
    ".tga", ".dpx",
}
REVIEW_EXTENSIONS = sorted(VIDEO_EXTENSIONS | IMAGE_EXTENSIONS)


class ExtractWorkfileReviewFromFile(
    plugin.BlenderExtractor,
    publish.OptionalPyblishPluginMixin,
):
    """Attach an image/video file from disk as review to the workfile."""

    label = "Extract Workfile Review (from file)"
    hosts = ["blender"]
    families = ["workfile"]
    # Run before 'ExtractThumbnailFromSource' (ExtractorOrder - 0.00001) and
    # 'ExtractReview' so the attached representation and 'thumbnailSource' are
    # in place for them to process.
    order = pyblish.api.ExtractorOrder - 0.1
    optional = True

    # Key of the file-picker attribute stored on the instance.
    attr_key = "review_filepath"

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        # Only expose the attribute on instances this plugin runs on
        # (i.e. the workfile instance).
        if not cls.instance_matches_plugin_families(instance):
            return []

        return [
            FileDef(
                cls.attr_key,
                folders=False,
                extensions=REVIEW_EXTENSIONS,
                allow_sequences=False,
                single_item=True,
                label="Review file",
                tooltip=(
                    "Attach an existing image or video file as the review "
                    "for this workfile publish.\n"
                    "Leave empty to publish the workfile without a review."
                ),
            )
        ]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        attr_values = self.get_attr_values_from_data(instance.data)
        source = self._resolve_path(attr_values.get(self.attr_key))
        if not source:
            self.log.debug(
                "No review file attached to workfile instance. Skipping."
            )
            return

        source = os.path.normpath(source)
        if not os.path.isfile(source):
            raise KnownPublishError(
                f"Attached workfile review file does not exist: {source}"
            )

        ext = os.path.splitext(source)[1].lower()
        if ext not in VIDEO_EXTENSIONS and ext not in IMAGE_EXTENSIONS:
            raise KnownPublishError(
                f"Unsupported review file extension '{ext}' for file: {source}"
            )

        # Copy the source into a staging dir so integrate transfers it to the
        # publish location instead of moving the artist's original file.
        staging_dir = self.staging_dir(instance)
        filename = os.path.basename(source)
        destination = os.path.join(staging_dir, filename)
        if os.path.normpath(destination) != source:
            shutil.copy2(source, destination)

        # Resolve fps. Core's 'ExtractReview' reads it from the *instance*
        # (not the representation), and the workfile instance normally has no
        # fps, so make sure it is set to avoid a KeyError during transcoding.
        fps = instance.data.get("fps")
        if fps is None:
            fps = instance.context.data.get("fps")
        if fps is None:
            fps = 25.0
            self.log.warning(
                "No fps found on instance or context; "
                "defaulting workfile review fps to 25.0."
            )
        instance.data["fps"] = fps

        representation = {
            "name": ext.lstrip("."),
            "ext": ext.lstrip("."),
            "files": filename,
            "stagingDir": staging_dir,
            "tags": ["review"],
        }
        if fps is not None:
            representation["fps"] = fps

        instance.data.setdefault("representations", []).append(representation)
        self.log.info(f"Attached review file to workfile: {source}")

        # Ensure the workfile instance is treated as reviewable by core
        # plugins (ExtractReview / integrate) that key off the 'review'
        # family.
        families = instance.data.setdefault("families", [])
        if "review" not in families:
            families.append("review")

        # Let the core 'ExtractThumbnailFromSource' plugin build a properly
        # sized thumbnail from the attached file (handles both images and
        # videos). Only set it if a thumbnail isn't already provided.
        if not instance.data.get("thumbnailSource") and not self._has_thumbnail(
            instance
        ):
            instance.data["thumbnailSource"] = source

    def _resolve_path(self, file_value):
        """Return an absolute path from a single-item ``FileDef`` value.

        A single-item ``FileDef`` stores a dict of the form
        ``{"directory": str, "filenames": [str, ...]}``. A plain string path
        is also accepted for robustness.
        """
        if isinstance(file_value, str):
            return file_value.strip() or None

        if not isinstance(file_value, dict):
            return None

        directory = file_value.get("directory")
        filenames = file_value.get("filenames") or []
        if not directory or not filenames:
            return None

        return os.path.join(directory, filenames[0])

    def _has_thumbnail(self, instance):
        for repre in instance.data.get("representations", []):
            if repre.get("thumbnail") or "thumbnail" in repre.get("tags", []):
                return True
        return False
