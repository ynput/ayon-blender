import attr


@attr.s
class LayerMetadata(object):
    """Data class for Render Layer metadata."""
    frameStart = attr.ib()
    frameEnd = attr.ib()


@attr.s
class RenderProduct(object):
    """
    Getting Colorspace as Specific Render Product Parameter for submitting
    publish job.
    """
    colorspace = attr.ib()  # colorspace
    view = attr.ib()        # OCIO view transform
    productName = attr.ib(default=None)


class ARenderProduct(object):
    def __init__(self, frame_start, frame_end):
        """Constructor."""
        # Initialize
        self.layer_data = self._get_layer_data(frame_start, frame_end)
        self.layer_data.products = self.get_render_products()

    def _get_layer_data(
        self,
        frame_start: int,
        frame_end: int
    ) -> LayerMetadata:
        return LayerMetadata(
            frameStart=int(frame_start),
            frameEnd=int(frame_end),
        )

    def get_render_products(self):
        """To be implemented by renderer class.
        This should return a list of RenderProducts.
        Returns:
            list: List of RenderProduct
        """
        return [
            RenderProduct(
                colorspace="sRGB",
                view="ACES 1.0",
                productName=""
            )
        ]
