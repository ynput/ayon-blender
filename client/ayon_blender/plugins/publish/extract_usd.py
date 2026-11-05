import os
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
    export_mesh_colors = True
    export_textures_mode = "KEEP"
    generate_preview_surface = True
    generate_materialx_network = False
    use_instancing = True

    overrides: list[str] = []

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
            "export_mesh_colors": attribute_values.get("export_mesh_colors", self.export_mesh_colors),
            "generate_preview_surface": attribute_values.get(
                "generate_preview_surface", self.generate_preview_surface
            ),
            "generate_materialx_network": attribute_values.get(
                "generate_materialx_network", self.generate_materialx_network
            ),
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

        export_textures_mode = attribute_values.get(
            "export_textures_mode",
            self.export_textures_mode
        )
        # `export_textures_mode` replaced the `export_textures` boolean in the
        # USD exporter: it exists since Blender 4.2 and is the only variant in
        # 5.0+, so pass whichever one this exporter supports.
        # See: https://docs.blender.org/api/current/bpy.ops.wm.html#bpy.ops.wm.usd_export  # noqa
        usd_export_properties = (
            bpy.ops.wm.usd_export.get_rna_type().properties
        )
        if "export_textures_mode" in usd_export_properties:
            kwargs["export_textures_mode"] = export_textures_mode
        else:
            kwargs["export_textures"] = export_textures_mode == "NEW"

        # Only `NEW` copies every texture next to the USD, so only then the USD
        # may use relative paths. `KEEP`/`PRESERVE` keep references to textures
        # which stay where they are, so those have to stay absolute.
        use_relative_paths = export_textures_mode == "NEW"
        # Export USD
        with bpy.context.temp_override(**context):
            bpy.ops.wm.usd_export(
                # Override the `/root` default value. If left as an empty
                # string, Blender will use the top-level object as the root prim.
                filepath=filepath,
                root_prim_path="",
                selected_objects_only=True,
                relative_paths=use_relative_paths,
                **kwargs
            )

        plugin.deselect_all()

        # Textures written by the export are referenced relative to the USD, so
        # they have to be published beside it. This applies to every mode:
        # `KEEP`/`PRESERVE` publish only the generated ones, `NEW` all of them.
        self.collect_and_transfer_textures(instance, stagingdir)

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

        visible = publish_attributes.get("convert_orientation", cls.convert_orientation)

        orientation_axes = {
            "X": "X",
            "Y": "Y",
            "Z": "Z",
            "NEGATIVE_X": "-X",
            "NEGATIVE_Y": "-Y",
            "NEGATIVE_Z": "-Z",
        }

        overrides: set[str] = set(cls.overrides)
        if not overrides:
            return defs

        override_defs = {
            "convert_orientation": BoolDef(
                "convert_orientation",
                label="Convert Orientation",
                tooltip="Convert orientation axis to a different convention"
                        " to match other applications.",
                default=cls.convert_orientation,
            ),
            "forward_axis": EnumDef(
                "forward_axis",
                label="Forward Axis",
                items=orientation_axes,
                default="Z",
                tooltip="Forward Axis for orientation conversion.",
                visible=visible,
            ),
            "up_axis": EnumDef(
                "up_axis",
                label="Up Axis",
                items=orientation_axes,
                default="Y",
                tooltip="Up Axis for orientation conversion.",
                visible=visible,
            ),
            "export_animation": BoolDef(
                "export_animation",
                label="Export Animation",
                tooltip="Whether to export animation data or not.",
                default=cls.export_animation,
            ),
            "export_hair": BoolDef(
                "export_hair",
                label="Export Hair",
                tooltip="Whether to export hair/fur systems or not.",
                default=cls.export_hair,
            ),
            "export_uvmaps": BoolDef(
                "export_uvmaps",
                label="Export UV Maps",
                tooltip="Whether to export UV map data or not.",
                default=cls.export_uvmaps,
            ),
            "export_normals": BoolDef(
                "export_normals",
                label="Export Normals",
                tooltip="Whether to export normal data or not.",
                default=cls.export_normals,
            ),
            "export_materials": BoolDef(
                "export_materials",
                label="Export Materials",
                tooltip="Whether to export material assignments and data or"
                        " not.",
                default=cls.export_materials,
            ),
            "export_mesh_colors": BoolDef(
                "export_mesh_colors",
                label="Export Mesh Colors",
                tooltip="Whether to export mesh color data or not.",
                default=cls.export_mesh_colors,
            ),
            "generate_preview_surface": BoolDef(
                "generate_preview_surface",
                label="Generate Preview Surface",
                tooltip="Whether to generate a preview surface for exported meshes or not.",
                default=cls.generate_preview_surface,
            ),
            "generate_materialx_network": BoolDef(
                "generate_materialx_network",
                label="Generate MaterialX Network",
                tooltip="Whether to generate a MaterialX network for exported materials or not.",
                default=cls.generate_materialx_network,
            ),
            "export_textures_mode": EnumDef(
                "export_textures_mode",
                label="Export Textures Mode",
                items={
                    "PRESERVE": "Preserve",
                    "KEEP": "Keep",
                    "NEW": "New",
                },
                tooltip="Mode for exporting textures in USD export.",
                default=cls.export_textures_mode,
            ),
            "use_instancing": BoolDef(
                "use_instancing",
                label="Instancing",
                tooltip="Whether to use USD instancing for duplicated objects"
                        " or not.",
                default=cls.use_instancing,
            ),
        }

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

    def collect_and_transfer_textures(self, instance, stagingdir):
        """Queue the textures the USD export wrote for publication.

        Blender writes generated (packed/generated image) textures into
        `<stagingdir>/textures` and references them relative to the USD, so they
        are transferred into a `textures` folder beside the published USD. This
        has to run after the export and applies to every texture mode: `KEEP`
        and `PRESERVE` only write the generated textures there, `NEW` writes all
        of them.

        Only the USD is part of the instance representations; the textures are
        auxiliary file transfers.

        Args:
            instance (pyblish.api.Instance): The instance to add the transfers
                to.
            stagingdir (str): The staging directory of the extracted USD.
        """
        texture_dir = os.path.join(stagingdir, "textures")
        if not os.path.isdir(texture_dir):
            # No textures were exported (e.g. `KEEP`/`PRESERVE` without packed
            # or generated images, or a scene without any texture).
            return

        publish_dir = instance.data["publishDir"]
        transfers = instance.data.setdefault("transfers", [])
        for root, _dirs, files in os.walk(texture_dir):
            for file_name in files:
                src = os.path.join(root, file_name)
                # Keep the layout of the `textures` folder, the USD references
                # its textures relative to itself.
                relative_filepath = os.path.relpath(src, texture_dir)
                dst = os.path.join(publish_dir, "textures", relative_filepath)
                transfers.append([src, dst])


class ExtractModelUSD(ExtractUSD):
    """Extract model as USD."""

    label = "Extract USD (Model)"
    hosts = ["blender"]
    families = ["model"]

    # Driven by settings
    optional = True
