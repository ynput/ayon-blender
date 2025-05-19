# -*- coding: utf-8 -*-
"""Converter for legacy Blender products."""
from ayon_core.pipeline.create.creator_plugins import ProductConvertorPlugin
from ayon_blender.api.lib import imprint
from ayon_blender.api.pipeline import AYON_PROPERTY, AVALON_PROPERTY


class BlenderLegacyConvertor(ProductConvertorPlugin):
    """Find and convert any legacy products in the scene.

    This Converter will find all legacy products in the scene and will
    transform them to the current system. Since the old products doesn't
    retain any information about their original creators, the only mapping
    we can do is based on their product types.

    Its limitation is that you can have multiple creators creating product
    of the same product type and there is no way to handle it. This code
    should nevertheless cover all creators that came with ayon.

    """
    identifier = "io.ayon.creators.blender.legacy"
    product_type_to_id = {
        "action": "io.ayon.creators.blender.action",
        "camera": "io.ayon.creators.blender.camera",
        "animation": "io.ayon.creators.blender.animation",
        "blendScene": "io.ayon.creators.blender.blendscene",
        "layout": "io.ayon.creators.blender.layout",
        "model": "io.ayon.creators.blender.model",
        "pointcache": "io.ayon.creators.blender.pointcache",
        "render": "io.ayon.creators.blender.render",
        "review": "io.ayon.creators.blender.review",
        "rig": "io.ayon.creators.blender.rig",
        "workfile": "io.ayon.creators.blender.workfile",
    }

    def __init__(self, *args, **kwargs):
        super(BlenderLegacyConvertor, self).__init__(*args, **kwargs)
        self.legacy_instances = {}

    def find_instances(self):
        """Find legacy products in the scene.

        Legacy products are the ones that doesn't have `creator_identifier`
        parameter on them.

        This is using cached entries done in
        :py:meth:`~BlenderCreator.cache_instance_data()`

        """
        self.legacy_instances = self.collection_shared_data.get(
            "blender_cached_legacy_instances")
        if not self.legacy_instances:
            return
        self.add_convertor_item(
            "Found {} incompatible product{}".format(
                len(self.legacy_instances),
                "s" if len(self.legacy_instances) > 1 else ""
            )
        )

    def convert(self):
        """Convert all legacy products to current.

        It is enough to add `creator_identifier` and `instance_node`.

        """
        if not self.legacy_instances:
            return

        for product_type, instance_nodes in self.legacy_instances.items():
            if product_type in self.product_type_to_id:
                for instance_node in instance_nodes:
                    creator_identifier = self.product_type_to_id[product_type]
                    self.log.info(
                        "Converting {} to {}".format(instance_node.name,
                                                     creator_identifier)
                    )
                    imprint(instance_node, data={
                        "creator_identifier": creator_identifier
                    })
                    avalon_prop = instance_node.get(AVALON_PROPERTY)
                    if not avalon_prop:
                        continue
                    instance_node[AYON_PROPERTY] = avalon_prop
                    del instance_node[AVALON_PROPERTY]
