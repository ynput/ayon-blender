"""Set Context Placeholder Plugin for Blender Workfile Build."""
from ayon_blender.api.workfile_template_builder import (
    BlenderPlaceholderPlugin
)
from ayon_blender.api.pipeline import set_context_settings
from ayon_core.lib import BoolDef


class SetContextBlenderPlaceholderPlugin(BlenderPlaceholderPlugin):
    """Set context variables for the workfile build.
    This placeholder allows the workfile build process to
    set context variables dynamically.

    """

    identifier = "blender.set_context"
    label = "Set Context Settings"

    use_selection_as_parent = False

    def get_placeholder_options(self, options=None):
        options = options or {}
        return [
            BoolDef(
                "resolution",
                label="Set Resolution",
                tooltip="Set Resolution context variable "
                        "based on the scene settings",
                default=options.get("resolution", True),
            ),
            BoolDef(
                "frame_range",
                label="Set Frame Range",
                tooltip="Set Frame Range context variable "
                        "based on the scene settings",
                default=options.get("frame_range", True),
            ),
            BoolDef(
                "scene_units",
                label="Set Scene Units",
                tooltip="Set Scene Units context variable "
                        "based on the scene settings",
                default=options.get("scene_units", False),
            )
        ]

    def populate_placeholder(self, placeholder):
        self.set_context_settings(placeholder)
        if not placeholder.data.get("keep_placeholder", True):
            self.delete_placeholder(placeholder)

    def set_context_settings(self, placeholder):
        """Set context settings for the placeholder.

        Args:
            placeholder (dict): placeholder data
        """
        placeholder_context_data = {
            "resolution": placeholder.data.get("resolution", True),
            "frame_range": placeholder.data.get("frame_range", True),
            "scene_units": placeholder.data.get("scene_units", False),
        }
        set_context_settings(**placeholder_context_data)
