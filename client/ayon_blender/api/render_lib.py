import os
from pathlib import Path
from typing import Optional
import bpy

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_current_project_name
from . import lib


def get_default_render_folder(project_settings) -> str:
    """Get default render folder from blender settings."""
    return project_settings["blender"]["RenderSettings"][
        "default_render_image_folder"
    ]


def get_aov_separator(project_settings) -> str:
    """Get aov separator from blender settings."""
    aov_sep = project_settings["blender"]["RenderSettings"]["aov_separator"]

    if aov_sep == "dash":
        return "-"
    elif aov_sep == "underscore":
        return "_"
    elif aov_sep == "dot":
        return "."
    else:
        raise ValueError(f"Invalid aov separator: {aov_sep}")


def get_image_format(project_settings) -> str:
    """Get image format from blender settings."""
    return project_settings["blender"]["RenderSettings"]["image_format"]


def get_multilayer(project_settings) -> bool:
    """Get multilayer from blender settings."""
    return project_settings["blender"]["RenderSettings"]["multilayer_exr"]


def get_renderer(project_settings) -> str:
    """Get renderer from blender settings."""
    return project_settings["blender"]["RenderSettings"]["renderer"]


def get_compositing(project_settings) -> bool:
    """Get whether 'Composite' render is enabled from blender settings."""
    return project_settings["blender"]["RenderSettings"]["compositing"]


def set_render_format(ext: str, multilayer: bool):
    """Set Blender scene to save render file with the right extension"""
    bpy.context.scene.render.use_file_extension = True
    image_settings = bpy.context.scene.render.image_settings

    if ext == "exr":
        image_settings.file_format = (
            "OPEN_EXR_MULTILAYER" if multilayer else "OPEN_EXR")
    elif ext == "bmp":
        image_settings.file_format = "BMP"
    elif ext == "rgb":
        image_settings.file_format = "IRIS"
    elif ext == "png":
        image_settings.file_format = "PNG"
    elif ext == "jpeg":
        image_settings.file_format = "JPEG"
    elif ext == "jp2":
        image_settings.file_format = "JPEG2000"
    elif ext == "tga":
        image_settings.file_format = "TARGA"
    elif ext == "tif":
        image_settings.file_format = "TIFF"


def get_file_format_extension(file_format: str) -> str:
    """Convert Blender file format to file extension."""
    # TODO: Figure out if Blender has a native way to convert to extensions
    if file_format == "OPEN_EXR_MULTILAYER":
        return "exr"
    elif file_format == "OPEN_EXR":
        return "exr"
    elif file_format == "BMP":
        return "bmp"
    elif file_format == "IRIS":
        return "rgb"
    elif file_format == "PNG":
        return "png"
    elif file_format == "JPEG":
        return "jpeg"
    elif file_format == "JPEG2000":
        return "jp2"
    elif file_format == "TARGA":
        return "tga"
    elif file_format == "TIFF":
        return "tif"
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def set_render_passes(settings, renderer, view_layers):
    """Set render passes for the current view layer

    Args:
        settings (dict): The project settings.
        renderer (str): The renderer to use, either CYCLES or BLENDER_EEVEE.
        view_layers (list[bpy.types.ViewLayer]): The list of view layers to
        set the passes for.
    """
    aov_list = set(settings["blender"]["RenderSettings"]["aov_list"])
    existing_aov_list = set(existing_aov_options(renderer, view_layers))
    aov_list = aov_list.union(existing_aov_list)
    custom_passes = settings["blender"]["RenderSettings"]["custom_passes"]
    # Common passes for both renderers
    for vl in view_layers:
        if renderer == "BLENDER_EEVEE":
            # Eevee exclusive passes
            aov_options = get_aov_options(renderer)
            eevee_attrs: set[str] = {
                "use_pass_bloom",
                "use_pass_transparent",
                "use_pass_volume_direct"
            }
            for pass_name, attr in aov_options.items():
                target = vl.eevee if attr in eevee_attrs else vl
                ver_major, ver_minor, _ = lib.get_blender_version()
                if ver_major >= 3 and ver_minor > 6:
                    if attr == "use_pass_bloom":
                        continue
                setattr(target, attr, pass_name in aov_list)
        elif renderer == "CYCLES":
            # Cycles exclusive passes
            aov_options = get_aov_options(renderer)
            cycle_attrs: set[str] = {
                "denoising_store_passes", "pass_debug_sample_count",
                "use_pass_volume_direct", "use_pass_volume_indirect",
                "use_pass_shadow_catcher"
            }
            for pass_name, attr in aov_options.items():
                target = vl.cycles if attr in cycle_attrs else vl
                setattr(target, attr, pass_name in aov_list)

        aovs_names: set[str] = {aov.name for aov in vl.aovs}
        for custom_pass in custom_passes:
            custom_pass_name = custom_pass["attribute"]
            if custom_pass_name not in aovs_names:
                aov = vl.aovs.add()
                aov.name = custom_pass_name
            else:
                aov = vl.aovs[custom_pass_name]
            aov.type = custom_pass["value"]

    return list(aov_list), custom_passes


def get_aov_options(renderer: str) -> dict[str, str]:
    """Return the available AOV options based on the renderer name."""
    aov_options = {
        "combined": "use_pass_combined",
        "z": "use_pass_z",
        "mist": "use_pass_mist",
        "normal": "use_pass_normal",
        "diffuse_light": "use_pass_diffuse_direct",
        "diffuse_color": "use_pass_diffuse_color",
        "specular_light": "use_pass_glossy_direct",
        "specular_color": "use_pass_glossy_color",
        "emission": "use_pass_emit",
        "environment": "use_pass_environment",
        "ao": "use_pass_ambient_occlusion",
        "cryptomatte_object": "use_pass_cryptomatte_object",
        "cryptomatte_material": "use_pass_cryptomatte_material",
        "cryptomatte_asset": "use_pass_cryptomatte_asset",
    }
    if renderer == "BLENDER_EEVEE":
        eevee_options = {
            "shadow": "use_pass_shadow",
            "volume_light": "use_pass_volume_direct",
            "bloom": "use_pass_bloom",
            "transparent": "use_pass_transparent",
            "cryptomatte_accurate": "use_pass_cryptomatte_accurate",
        }
        aov_options.update(eevee_options)
    elif renderer == "CYCLES":
        cycles_options = {
            "position": "use_pass_position",
            "vector": "use_pass_vector",
            "uv": "use_pass_uv",
            "denoising": "denoising_store_passes",
            "object_index": "use_pass_object_index",
            "material_index": "use_pass_material_index",
            "sample_count": "pass_debug_sample_count",
            "diffuse_indirect": "use_pass_diffuse_indirect",
            "specular_indirect": "use_pass_glossy_indirect",
            "transmission_direct": "use_pass_transmission_direct",
            "transmission_indirect": "use_pass_transmission_indirect",
            "transmission_color": "use_pass_transmission_color",
            "volume_light": "use_pass_volume_direct",
            "volume_indirect": "use_pass_volume_indirect",
            "shadow": "use_pass_shadow_catcher",
        }
        aov_options.update(cycles_options)

    return aov_options


def existing_aov_options(
    renderer: str, view_layers: list["bpy.types.ViewLayer"]
) -> list[str]:
    aov_list = []
    aov_options = get_aov_options(renderer)
    for vl in view_layers:
        if renderer == "BLENDER_EEVEE":
            eevee_attrs = ["use_pass_shadow", "cryptomatte_accurate"]
            for pass_name, attr in aov_options.items():
                target = vl if attr in eevee_attrs else vl.eevee
                if getattr(target, attr, False):
                    aov_list.append(pass_name)

        elif renderer == "CYCLES":
            cycle_attrs = [
                "denoising_store_passes", "pass_debug_sample_count",
                "use_pass_volume_direct", "use_pass_volume_indirect",
                "use_pass_shadow_catcher"
            ]
            for pass_name, attr in aov_options.items():
                target = vl.cycles if attr in cycle_attrs else vl
                if getattr(target, attr, False):
                    aov_list.append(pass_name)

    return aov_list


def _create_aov_slot(
    slots: "bpy.types.RenderSlots",
    variant_name: str,
    aov_sep: str,
    renderpass_name: str,
    is_multi_exr: bool,
    render_layer: str,
) -> "bpy.types.RenderSlot":
    """Add a new render output slot to the slots.

    The slots usually are the file slots of the compositor output node.
    The filepath is based on the render layer, variant name and render pass.

    If it's multi-exr, the slot will be named after the render pass only.

    Returns:
        The created slot

    """
    filename = (
        f"{render_layer}/"
        f"{variant_name}_{render_layer}{aov_sep}{renderpass_name}.####"
    )
    return slots.new(renderpass_name if is_multi_exr else filename)


def get_base_render_output_path(
    variant_name: str,
    multi_exr: Optional[bool] = None,
    project_settings: Optional[dict] = None
) -> str:
    """Return the base render output path for the given variant name.

    The output path is based on the AYON project settings and the current
    Blender scene workfile path.

    If the render settings are not set to multi-EXR then only the base path
    is returned, otherwise the full path to the render output file is returned.

    """
    workfile_filepath = Path(bpy.data.filepath)
    assert workfile_filepath, "Workfile not saved. Please save the file first."

    render_folder = get_default_render_folder(project_settings)
    aov_sep = get_aov_separator(project_settings)
    if multi_exr is None:
        multi_exr = get_multilayer(project_settings)

    workfile_dir = workfile_filepath.parent
    workfile_filename = Path(workfile_filepath.name).stem
    base_folder = Path.joinpath(workfile_dir, render_folder, workfile_filename)
    if not multi_exr:
        # If not multi-exr, we only supply the root folder to render to.
        return str(base_folder)

    filename = f"{variant_name}{aov_sep}beauty.####"
    filepath = base_folder / filename
    return str(filepath)


def create_render_node_tree(
    variant_name: str,
    render_layer_nodes: set["bpy.types.CompositorNodeRLayers"],
    project_settings: dict,
) -> "bpy.types.CompositorNodeOutputFile":
    """Create a Compositor node tree for rendering based on project settings.

    Arguments:
        variant_name (str): The name of the variant to use in the output file
            names.
        view_layers (list[bpy.types.ViewLayer]): The list of view layers to
            create render layer nodes for.
        project_settings (dict): The project settings dictionary.
    """
    # Set the scene to use the compositor node tree to render
    bpy.context.scene.use_nodes = True

    aov_sep = get_aov_separator(project_settings)
    ext = get_image_format(project_settings)
    multilayer = get_multilayer(project_settings)
    compositing = get_compositing(project_settings)

    tree = bpy.context.scene.node_tree

    comp_composite_type = "CompositorNodeComposite"

    # Find existing 'Composite' node
    composite_node = None
    for node in tree.nodes:
        if node.bl_idname == comp_composite_type:
            composite_node = node
            break

    # Create a new output node
    output: bpy.types.CompositorNodeOutputFile = tree.nodes.new(
        "CompositorNodeOutputFile"
    )
    output.name = variant_name
    output.label = variant_name

    # By default, match output format from scene file format
    image_settings = bpy.context.scene.render.image_settings
    output.format.file_format = image_settings.file_format
    multi_exr: bool = ext == "exr" and multilayer

    # Define the base path for the File Output node.
    output.base_path = get_base_render_output_path(
        variant_name, project_settings=project_settings
    )

    slots = output.layer_slots if multi_exr else output.file_slots
    slots.clear()

    # Create a new socket for the beauty output
    pass_name = "beauty"
    for render_layer_node in render_layer_nodes:
        render_layer = render_layer_node.layer
        slot = _create_aov_slot(
            slots, variant_name, aov_sep, pass_name, multi_exr, render_layer
        )
        tree.links.new(render_layer_node.outputs["Image"], slot)

    last_found_renderlayer_node = next(
        (node for node in reversed(list(render_layer_nodes))), None
    )
    if compositing and last_found_renderlayer_node:
        # Create a new socket for the composite output
        # with only the one view layer
        pass_name = "composite"
        render_layer = last_found_renderlayer_node.layer
        slot = _create_aov_slot(
            slots, variant_name, aov_sep, pass_name, multi_exr, render_layer
        )
        # If there's a composite node, we connect its 'Image' input with the
        # new slot on the output
        if composite_node:
            for link in composite_node.inputs["Image"].links:
                tree.links.new(link.from_socket, slot)
                break

    # For each active render pass, we add a new socket to the output node
    # and link it
    exclude_sockets: set[str] = {"Image", "Alpha", "Noisy Image"}
    for render_layer_node in render_layer_nodes:
        # Get the enabled output sockets, that are the active passes for the
        # render.
        render_layer = render_layer_node.layer
        for output_socket in render_layer_node.outputs:
            if output_socket.name in exclude_sockets:
                continue

            if not output_socket.enabled:
                continue

            slot = _create_aov_slot(
                slots,
                variant_name,
                aov_sep,
                output_socket.name,
                multi_exr,
                render_layer,
            )

            tree.links.new(output_socket, slot)

    return output


def prepare_rendering(
    variant_name: str, project_settings: Optional[dict] = None
) -> "bpy.types.CompositorNodeOutputFile":
    """Initialize render setup using render settings from project settings."""
    assert bpy.data.filepath, "Workfile not saved. Please save the file first."

    if project_settings is None:
        project_name: str = get_current_project_name()
        project_settings = get_project_settings(project_name)

    ext = get_image_format(project_settings)
    multilayer = get_multilayer(project_settings)
    renderer = get_renderer(project_settings)
    ver_major, ver_minor, _ = lib.get_blender_version()
    if renderer == "BLENDER_EEVEE" and (
        ver_major >= 4 and ver_minor >=2
    ):
        renderer = "BLENDER_EEVEE_NEXT"

    # Set scene render settings
    set_render_format(ext, multilayer)
    bpy.context.scene.render.engine = renderer
    view_layers = bpy.context.scene.view_layers
    set_render_passes(project_settings, renderer, view_layers)

    # Use selected renderlayer nodes, or assume we want a renderlayer node for
    # each view layer so we retrieve all of them.
    node_tree = bpy.context.scene.node_tree
    selected_renderlayer_nodes = []
    for node in node_tree.nodes:
        if node.bl_idname == "CompositorNodeRLayers" and node.select:
            selected_renderlayer_nodes.append(node)

    if selected_renderlayer_nodes:
        render_layer_nodes = selected_renderlayer_nodes
    else:
        render_layer_nodes = get_or_create_render_layer_nodes(
            node_tree, view_layers
        )

    # Generate Compositing nodes
    output_node = create_render_node_tree(
        variant_name,
        render_layer_nodes,
        project_settings
    )

    # Clear the scene render filepath, so that the outputs are handled only by
    # the file output nodes in the compositor.
    tmp_render_path = os.path.join(os.getenv("AYON_WORKDIR"), "renders", "tmp")
    tmp_render_path = tmp_render_path.replace("\\", "/")
    os.makedirs(tmp_render_path, exist_ok=True)
    bpy.context.scene.render.filepath = tmp_render_path

    return output_node


def get_or_create_render_layer_nodes(
    tree: "bpy.types.CompositorNodeTree",
    view_layers: list["bpy.types.ViewLayer"],
) -> set[bpy.types.CompositorNodeRLayers]:
    """Get existing render layer nodes or create new ones."""
    view_layers: set[str] = {view_layer.name for view_layer in view_layers}

    # Find existing render layer nodes for each view layer
    render_layer_nodes = set()
    found_view_layers = set()
    for node in tree.nodes:
        if node.bl_idname != "CompositorNodeRLayers":
            continue

        # Skip if already found a render layer node for this view layer.
        if node.layer in found_view_layers:
            continue

        # Skip if the view layer is not meant to be included.
        if node.layer not in view_layers:
            continue

        found_view_layers.add(node.layer)
        render_layer_nodes.add(node)

    # Generate the missing render layer nodes
    missing_view_layers = view_layers - found_view_layers
    for view_layer in missing_view_layers:
        render_layer_node = tree.nodes.new("CompositorNodeRLayers")
        render_layer_node.layer = view_layer.name
        render_layer_nodes.add(render_layer_node)

    return render_layer_nodes