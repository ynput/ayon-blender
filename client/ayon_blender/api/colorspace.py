import attr


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
