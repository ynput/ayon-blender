import os
from collections import OrderedDict

import bpy

from ayon_core.pipeline import KnownPublishError, OptionalPyblishPluginMixin
from ayon_core.lib import BoolDef, EnumDef
from ayon_blender.api import plugin, lib


class ExtractUSD(plugin.BlenderExtractor,
                 OptionalPyblishPluginMixin):
    """Extract as USD."""

    label = "Extract USD"
    hosts = ["blender"]
    families = ["usd"]

    # Settings
    convert_orientation = False
    export_animation = False
    export_hair = False
    export_uvmaps = True
    export_normals = True
    export_materials = True
    use_instancing = True

    overrides = []

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        # Ignore runtime instances (e.g. USD layers)
        # TODO: This is better done via more specific `families`
        if not instance.data.get("transientData", {}).get("instance_node"):
            return

        # Define extract output file path
        stagingdir = self.staging_dir(instance)
        filename = f"{instance.name}.usd"
        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.debug("Performing extraction..")

        # Select all members to "export selected"
        plugin.deselect_all()

        selected = []
        for obj in instance:
            if isinstance(obj, bpy.types.Object):
                obj.select_set(True)
                selected.append(obj)

        root = lib.get_highest_root(objects=instance[:])
        if not root:
            instance_node = instance.data["transientData"]["instance_node"]
            raise KnownPublishError(
                f"No root object found in instance: {instance_node.name}"
            )
        self.log.debug(f"Exporting using active root: {root.name}")

        context = plugin.create_blender_context(
            active=root, selected=selected)

        attribute_values = self.get_attr_values_from_data(instance.data)
        convert_orientation = attribute_values.get(
            "convert_orientation",
            self.convert_orientation
        )
        kwargs = {
            "convert_orientation": convert_orientation,
            "export_global_forward_selection": attribute_values.get("forward_axis", "Z"),
            "export_global_up_selection": attribute_values.get("up_axis", "Y"),
            "export_animation": attribute_values.get("export_animation", self.export_animation),
            "export_hair": attribute_values.get("export_hair", self.export_hair),
            "export_uvmaps": attribute_values.get("export_uvmaps", self.export_uvmaps),
            "export_normals": attribute_values.get("export_normals", self.export_normals),
            "export_materials": attribute_values.get("export_materials", self.export_materials),
            "use_instancing": attribute_values.get("use_instancing", self.use_instancing),
        }

        blender_version = lib.get_blender_version()
        if blender_version < (4, 2, 1):
            kwargs = {}
            if convert_orientation:
                self.log.warning(
                    "Convert orientation was enabled for USD export but is not "
                    "supported in Blender < \"4.2.1\". Please update to at least Blender "
                    "4.2.1 to support it."
                )

        # See: https://docs.blender.org/api/current/bpy.ops.wm.html#bpy.ops.wm.usd_export  # noqa
        if blender_version >= (5, 0, 0):
            kwargs["export_textures_mode"] = "KEEP"
        else:
            kwargs["export_textures"] = False

        # Export USD
        with bpy.context.temp_override(**context):
            bpy.ops.wm.usd_export(
                # Override the `/root` default value. If left as an empty
                # string, Blender will use the top-level object as the root prim.
                filepath=filepath,
                root_prim_path="",
                selected_objects_only=True,
                relative_paths=False,
                **kwargs
            )

        plugin.deselect_all()

        # Add representation
        representation = {
            'name': 'usd',
            'ext': 'usd',
            'files': filename,
            "stagingDir": stagingdir,
        }
        instance.data.setdefault("representations", []).append(representation)
        self.log.debug("Extracted instance '%s' to: %s",
                       instance.name, representation)

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        # Filtering of instance, if needed, can be customized
        if not cls.instance_matches_plugin_families(instance):
            return []

        # Attributes logic
        publish_attributes = cls.get_attr_values_from_data_for_plugin(
            cls, instance
        )

        defs = []

        visible = (
            publish_attributes.get("convert_orientation", cls.convert_orientation)
            | cls.convert_orientation
        )

        orientation_axes = {
            "X": "X",
            "Y": "Y",
            "Z": "Z",
            "NEGATIVE_X": "-X",
            "NEGATIVE_Y": "-Y",
            "NEGATIVE_Z": "-Z",
        }

        overrides = publish_attributes.get("overrides", cls.overrides)
        if not overrides:
            return defs

        override_defs = OrderedDict({
            "convert_orientation": BoolDef("convert_orientation",
                    label="Convert Orientation",
                    tooltip="Convert orientation axis to a different"
                    " convention to match other applications.",
                    default=cls.convert_orientation),
            "forward_axis": EnumDef("forward_axis",
                    label="Forward Axis",
                    items=orientation_axes,
                    default="Z",
                    visible=visible),
            "up_axis": EnumDef("up_axis",
                    label="Up Axis",
                    items=orientation_axes,
                    default="Y",
                    visible=visible),
            "export_animation": BoolDef(
                "export_animation",
                label="Export Animation",
                tooltip="Whether to export animation data or not.",
                default=cls.export_animation),
            "export_hair": BoolDef(
                "export_hair",
                label="Export Hair",
                tooltip="Whether to export hair/fur systems or not.",
                default=cls.export_hair),
            "export_uvmaps": BoolDef(
                "export_uvmaps",
                label="Export UV Maps",
                tooltip="Whether to export UV map data or not.",
                default=cls.export_uvmaps),
            "export_normals": BoolDef(
                "export_normals",
                label="Export Normals",
                tooltip="Whether to export normal data or not.",
                default=cls.export_normals),
            "export_materials": BoolDef(
                "export_materials",
                label="Export Materials",
                tooltip="Whether to export material assignments and data or not.",
                default=cls.export_materials),
            "use_instancing": BoolDef(
                "use_instancing",
                label="Instancing",
                tooltip="Whether to use USD instancing for duplicated objects or not.",
                default=cls.use_instancing),

        })

        for key, value in override_defs.items():
            if key not in overrides and key not in {"forward_axis", "up_axis"}:
                continue


            defs.append(value)

        return defs

    @classmethod
    def register_create_context_callbacks(cls, create_context):
        create_context.add_value_changed_callback(cls.on_values_changed)

    @classmethod
    def on_values_changed(cls, event):
        """Update instance attribute definitions on attribute changes."""

        # Update attributes if any of the following plug-in attributes
        # change:
        keys = ["convert_orientation"]

        for instance_change in event["changes"]:
            instance = instance_change["instance"]
            if not cls.instance_matches_plugin_families(instance):
                continue
            value_changes = instance_change["changes"]
            plugin_attribute_changes = cls.get_attr_values_from_data_for_plugin(
                cls, value_changes
            )

            if not any(key in plugin_attribute_changes for key in keys):
                continue

            # Update the attribute definitions
            new_attrs = cls.get_attr_defs_for_instance(
                event["create_context"], instance
            )
            instance.set_publish_plugin_attr_defs(cls.__name__, new_attrs)


class ExtractModelUSD(ExtractUSD):
    """Extract model as USD."""

    label = "Extract USD (Model)"
    hosts = ["blender"]
    families = ["model"]

    # Driven by settings
    optional = True
