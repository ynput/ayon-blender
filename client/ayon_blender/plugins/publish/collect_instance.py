import bpy

import pyblish.api

from ayon_core.pipeline.publish import KnownPublishError
from ayon_blender.api import plugin
from ayon_blender.api.pipeline import AVALON_PROPERTY


class CollectBlenderInstanceData(plugin.BlenderInstancePlugin):
    """Collect members of the instance.

    For a Collection this includes itself and all directly linked objects and
    their full hierarchy of children objects. It also includes direct child
    collections. It does *not* include objects or collections from collections
    inside the Collection (it does not recurse into nested collections).

    For an Object (e.g. instance asset group) this includes all its children
    hierarchy.

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
            # Note that for a `bpy.types.Collection` the `children` and
            # `children_recursive` only include child collections, not objects.
            # To get the linked objects (and their children) we first collect
            # the objects, and then add all their `children_recursive`.
            objects = list(instance_node.objects)
            members.update(objects)
            for obj in objects:
                members.update(obj.children_recursive)

            # Special case for animation instances, include armatures
            if instance.data["productType"] == "animation":
                for obj in instance_node.objects:
                    if obj.type == 'EMPTY' and obj.get(AVALON_PROPERTY):
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
