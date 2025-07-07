"""Load an animation in Blender."""

from typing import Dict, List, Optional

import bpy

from ayon_blender.api import plugin
from ayon_blender.api.pipeline import AVALON_PROPERTY


class BlendAnimationLoader(plugin.BlenderLoader):
    """Load animations from a .blend file.

    Warning:
        Loading the same asset more then once is not properly supported at the
        moment.
    """

    product_types = {"animation"}
    representations = {"blend"}

    label = "Link Animation"
    icon = "code-fork"
    color = "orange"

    def process_asset(
        self, context: dict, name: str, namespace: Optional[str] = None,
        options: Optional[Dict] = None
    ) -> Optional[List]:
        """
        Arguments:
            name: Use pre-defined name
            namespace: Use pre-defined namespace
            context: Full parenthood of representation to load
            options: Additional settings dictionary
        """
        libpath = self.filepath_from_context(context)

        with bpy.data.libraries.load(
            libpath, link=True, relative=False
        ) as (data_from, data_to):
            data_to.objects = data_from.objects
            data_to.actions = data_from.actions

        container = data_to.objects[0]

        assert container, "No asset group found"

        target_namespace = container.get(AVALON_PROPERTY).get('namespace', namespace)

        action = data_to.actions[0].make_local().copy()

        for obj in bpy.data.objects:
            if obj.get(AVALON_PROPERTY) and obj.get(AVALON_PROPERTY).get(
                    'namespace', namespace) == target_namespace:
                if obj.children[0]:
                    if not obj.children[0].animation_data:
                        obj.children[0].animation_data_create()
                    obj.children[0].animation_data.action = action
                break

        bpy.data.objects.remove(container)

        filename = bpy.path.basename(libpath)
        # Blender has a limit of 63 characters for any data name.
        # If the filename is longer, it will be truncated.
        if len(filename) > 63:
            filename = filename[:63]
        library = bpy.data.libraries.get(filename)
        bpy.data.libraries.remove(library)
