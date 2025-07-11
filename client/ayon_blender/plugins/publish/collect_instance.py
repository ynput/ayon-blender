from __future__ import annotations
import bpy

import pyblish.api

from ayon_core.lib import BoolDef
from ayon_core.pipeline import AYONPyblishPluginMixin
from ayon_core.pipeline.publish import KnownPublishError
from ayon_blender.api import plugin
from ayon_blender.api.constants import AYON_PROPERTY


class CollectBlenderInstanceData(plugin.BlenderInstancePlugin,
                                 AYONPyblishPluginMixin):
    """Collect members of the instance.

    For a Collection this includes itself and all directly linked objects and
    their full hierarchy of children objects. It also includes direct child
    collections. It does *not* include objects or collections from collections
    inside the Collection (it does not recurse into nested collections).

    For an Object (e.g. instance asset group) this includes all its children
    hierarchy and the Object itself.

    These members are then set on the instance as a list of objects.
    """

    order = pyblish.api.CollectorOrder
    hosts = ["blender"]
    families = ["model", "pointcache", "animation", "rig", "camera", "layout",
                "blendScene", "usd"]
    label = "Collect Instance"

    def process(self, instance):
        instance_node = instance.data["transientData"]["instance_node"]

        # Collect members of the instance
        members: set[str] = {instance_node}
        self.log.debug(f"Found instance node: {instance_node}")
        if isinstance(instance_node, bpy.types.Collection):
            # Add all linked objects to itself and all child collections
            objects = set(instance_node.all_objects)
            members.update(objects)

            # Add all object children recursively (hierarchy)
            # Note that for a `bpy.types.Collection` the `children` and
            # `children_recursive` only include child collections, not objects.
            # To get the linked objects (and their children) we first collect
            # the objects, and then add all their `children_recursive`.
            attr_values = self.get_attr_values_from_data(instance.data)
            if attr_values.get(
                "collection_include_object_children_recursive", True
            ):
                for obj in objects:
                    members.update(obj.children_recursive)

            # Add child collections
            members.update(instance_node.children)

            # Special case for animation instances, include armatures
            if instance.data["productType"] == "animation":
                for obj in instance_node.objects:
                    if obj.type == 'EMPTY' and obj.get(AYON_PROPERTY):
                        members.update(
                            child for child in obj.children
                            if child.type == 'ARMATURE'
                        )
        elif isinstance(instance_node, bpy.types.Object):
            members.update(instance_node.children_recursive)
        else:
            raise KnownPublishError(
                f"Unsupported instance node type '{type(instance_node)}' "
                f"for instance '{instance}'"
            )

        instance[:] = list(members)

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context, instance
    ):
        if not cls.instance_matches_plugin_families(instance):
            return []

        # If the instance is a collection, we provide an optional option
        # to include the children hierarchy of objects in the collection.
        instance_node = instance.transient_data.get("instance_node", None)
        if not isinstance(instance_node, bpy.types.Collection):
            return []

        return [
            BoolDef(
                "collection_include_object_children_recursive",
                label="Include Objects Hierarchy",
                default=True,
                tooltip=(
                    "If enabled, the children of objects in the collection "
                    "will be included in the instance members.\n"
                    "If disabled, only objects directly linked to the "
                    "collection will be included."
                )
            )
        ]
