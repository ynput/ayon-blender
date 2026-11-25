import logging

import attr
import bpy

log = logging.getLogger(__name__)


def set_scene_colorspace(
    scene: "bpy.types.Scene",
    display: str = "",
    view: str = "",
    look: str = "",
    working_space: str = "",
    sequencer_colorspace: str = "",
):
    """Set the scene color management and the blend file working space.

    Empty values are skipped. The display is set before the view and the view
    before the look because the available views depend on the display and the
    available looks depend on the view.

    Args:
        scene (bpy.types.Scene): Scene to set the color management on.
        display (str): OCIO display name.
        view (str): OCIO view name.
        look (str): OCIO look name, or 'None'.
        working_space (str): OCIO colorspace name for the blend file's
            working space. Requires Blender 5.0+.
        sequencer_colorspace (str): OCIO colorspace name for the sequencer.
    """
    if working_space:
        # Blender 4.x has no per blend file working space, it was added in
        # Blender 5.0. Remove this check once Blender 4 is no longer supported.
        if not hasattr(bpy.data, "colorspace"):
            log.warning(
                "Blender %s has no working color space. Skipping '%s'.",
                bpy.app.version_string, working_space
            )
        elif bpy.data.colorspace.working_space != working_space:
            try:
                bpy.ops.wm.set_working_color_space(
                    working_space=working_space, convert_colors=True
                )
            except TypeError as exc:
                log.warning("Unable to set working space: %s", exc)

    for settings, attribute, value in (
        (scene.display_settings, "display_device", display),
        (scene.view_settings, "view_transform", view),
        (scene.view_settings, "look", look),
        (scene.sequencer_colorspace_settings, "name", sequencer_colorspace),
    ):
        if not value:
            continue
        try:
            setattr(settings, attribute, value)
        except TypeError as exc:
            log.warning("Unable to set %s: %s", attribute, exc)


@attr.s
class RenderProduct(object):
    """
    Getting Colorspace as Specific Render Product Parameter for submitting
    publish job.
    """
    colorspace = attr.ib()  # OCIO source colorspace
    display = attr.ib()     # OCIO source display transform
    view = attr.ib()        # OCIO source view transform
    productName = attr.ib()


@attr.s
class LayerMetadata(object):
    """Data class for Render Layer metadata."""
    frameStart = attr.ib()
    frameEnd = attr.ib()
    products: list[RenderProduct] = attr.ib(factory=list)


class ARenderProduct(object):
    def __init__(self, frame_start, frame_end):
        """Constructor."""
        # Initialize
        self.layer_data = self._get_layer_data(frame_start, frame_end)

    def _get_layer_data(
        self,
        frame_start: int,
        frame_end: int
    ) -> LayerMetadata:
        return LayerMetadata(
            frameStart=int(frame_start),
            frameEnd=int(frame_end),
        )

    def add_render_product(
        self,
        product_name: str,
        colorspace="",
        display="",
        view=""):
        self.layer_data.products.append(
            RenderProduct(
                productName=product_name,
                colorspace=colorspace,
                display=display,
                view=view
            )
        )
