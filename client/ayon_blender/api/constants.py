import bpy


AVALON_INSTANCES = "AVALON_INSTANCES"
AYON_INSTANCES = "AYON_INSTANCES"
AVALON_CONTAINERS = "AVALON_CONTAINERS"
AYON_CONTAINERS = "AYON_CONTAINERS"
AVALON_PROPERTY = "avalon"
AYON_PROPERTY = "ayon"
IS_HEADLESS = bpy.app.background


# Object types that can be visible in a viewport capture (playblast).
# `GPENCIL` is the legacy Grease Pencil type used up to Blender 4.2 and
# `EMPTY` includes collection instances.
CAPTURE_OBJECT_TYPES = {
    "MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD",
    "VOLUME", "GPENCIL", "GREASEPENCIL", "EMPTY"
}

VALID_EXTENSIONS = [".blend", ".json", ".abc", ".fbx",
                    ".usd", ".usdc", ".usda", ".obj",
                    ".mtl"]
