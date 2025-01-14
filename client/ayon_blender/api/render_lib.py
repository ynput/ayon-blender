import os
from pathlib import Path
import bpy
import tempfile

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_current_project_name


def get_default_render_folder(settings):
    """Get default render folder from blender settings."""

    return (settings["blender"]
                    ["RenderSettings"]
                    ["default_render_image_folder"])


def get_aov_separator(settings):
    """Get aov separator from blender settings."""

    aov_sep = (settings["blender"]
                       ["RenderSettings"]
                       ["aov_separator"])

    if aov_sep == "dash":
        return "-"
    elif aov_sep == "underscore":
        return "_"
    elif aov_sep == "dot":
        return "."
    else:
        raise ValueError(f"Invalid aov separator: {aov_sep}")


def get_image_format(settings):
    """Get image format from blender settings."""

    return (settings["blender"]
                    ["RenderSettings"]
                    ["image_format"])


def get_multilayer(settings):
    """Get multilayer from blender settings."""

    return (settings["blender"]
                    ["RenderSettings"]
                    ["multilayer_exr"])


def get_renderer(settings):
    """Get renderer from blender settings."""

    return (settings["blender"]
                    ["RenderSettings"]
                    ["renderer"])


def get_compositing(settings):
    """Get compositing from blender settings."""

    return (settings["blender"]
                    ["RenderSettings"]
                    ["compositing"])


def get_render_product(output_path, name, aov_sep, view_layers):
    """
    Generate the path to the render product. Blender interprets the `#`
    as the frame number, when it renders.

    Args:
        file_path (str): The path to the blender scene.
        render_folder (str): The render folder set in settings.
        file_name (str): The name of the blender scene.
        instance (pyblish.api.Instance): The instance to publish.
        ext (str): The image format to render.
    """
    beauty_render_product = {}
    for view_layer in view_layers:
        vl_name = view_layer.name
        beauty_render_product[vl_name] = []
        output_dir = Path(f"{output_path}/{vl_name}")
        filepath = output_dir / name.lstrip("/")
        render_product = f"{filepath}_{vl_name}{aov_sep}beauty.####"
        beauty_render_product[vl_name].append(("beauty", os.path.normpath(render_product)))
    return beauty_render_product



def set_render_format(ext, multilayer):
    # Set Blender to save the file with the right extension
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


def set_render_passes(settings, renderer, view_layers):
    aov_list = set(settings["blender"]["RenderSettings"]["aov_list"])
    existing_aov_list = set(existing_aov_options(renderer, view_layers))
    aov_list = aov_list.union(existing_aov_list)
    custom_passes = settings["blender"]["RenderSettings"]["custom_passes"]
    # Common passes for both renderers
    for vl in view_layers:
        if renderer == "BLENDER_EEVEE":
            # Eevee exclusive passes
            aov_options = get_aov_options(renderer)
            eevee_attrs = ["use_pass_shadow", "cryptomatte_accurate"]
            for pass_name, attr in aov_options.items():
                target = vl if attr in eevee_attrs else vl.eevee
                setattr(target, attr, pass_name in aov_list)
        elif renderer == "CYCLES":
            # Cycles exclusive passes
            aov_options = get_aov_options(renderer)
            cycle_attrs = [
                "denoising_store_passes", "pass_debug_sample_count",
                "use_pass_volume_direct", "use_pass_volume_indirect",
                "use_pass_shadow_catcher"
            ]
            for pass_name, attr in aov_options.items():
                target = vl.cycles if attr in cycle_attrs else vl
                setattr(target, attr, pass_name in aov_list)

        aovs_names = [aov.name for aov in vl.aovs]
        for cp in custom_passes:
            cp_name = cp["attribute"]
            if cp_name not in aovs_names:
                aov = vl.aovs.add()
                aov.name = cp_name
            else:
                aov = vl.aovs[cp_name]
            aov.type = cp["value"]

    return list(aov_list), custom_passes


def get_aov_options(renderer):
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


def existing_aov_options(renderer, view_layers):
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


def _create_aov_slot(name, aov_sep, slots, rpass_name, multi_exr, output_path, render_layer):
    filename = f"{render_layer}/{name}_{render_layer}{aov_sep}{rpass_name}.####"
    slot = slots.new(rpass_name if multi_exr else filename)
    filepath = str(output_path / filename.lstrip("/"))

    return slot, filepath


def set_node_tree(
    output_path, name, aov_sep, ext, multilayer, compositing,
    view_layers
):
    # Set the scene to use the compositor node tree to render
    bpy.context.scene.use_nodes = True

    tree = bpy.context.scene.node_tree

    comp_layer_type = "CompositorNodeRLayers"
    output_type = "CompositorNodeOutputFile"
    compositor_type = "CompositorNodeComposite"

    # Get the Render Layer, Composite and the previous output nodes
    render_layer_nodes = set()
    composite_node = None
    old_output_node = None
    for node in tree.nodes:
        if node.bl_idname == comp_layer_type:
            render_layer_nodes.add(node)
        elif node.bl_idname == compositor_type:
            composite_node = node
        elif node.bl_idname == output_type and "AYON" in node.name:
            old_output_node = node
        if render_layer_nodes and composite_node and old_output_node:
            break

    # If there's not a Render Layers node, we create it
    if not render_layer_nodes:
        render_layer_nodes = create_node_with_new_view_layers(
            tree, comp_layer_type,
            view_layers, render_layer_nodes
        )
    else:
        missing_render_layer_nodes = set()
        orig_view_layers = {view_layer.name for view_layer in view_layers}
        missing_view_layers_by_nodes = {node.layer for node in render_layer_nodes}
        missing_view_layers_set = orig_view_layers - missing_view_layers_by_nodes
        missing_view_layers = [
            view_layer for view_layer in view_layers
            if view_layer.name in missing_view_layers_set
        ]
        missing_render_layer_nodes = create_node_with_new_view_layers(
            tree, comp_layer_type,
            missing_view_layers, missing_render_layer_nodes
        )
        render_layer_nodes.update(missing_render_layer_nodes)

    # Get the enabled output sockets, that are the active passes for the
    # render.
    # We also exclude some layers.
    exclude_sockets = ["Image", "Alpha", "Noisy Image"]
    render_aovs_dict = {}
    for render_layer_node in render_layer_nodes:
        render_dict = {
            render_layer_node: [
            socket
            for socket in render_layer_node.outputs
            if socket.enabled and socket.name not in exclude_sockets
        ]
    }
        render_aovs_dict.update(render_dict)
    # Create a new output node
    output = tree.nodes.new(output_type)

    image_settings = bpy.context.scene.render.image_settings
    output.format.file_format = image_settings.file_format

    slots = None

    # In case of a multilayer exr, we don't need to use the output node,
    # because the blender render already outputs a multilayer exr.
    multi_exr = ext == "exr" and multilayer
    slots = output.layer_slots if multi_exr else output.file_slots

    rn_layer_node = next((node for node in reversed(render_aovs_dict.keys())), None)
    output_dir = Path(f"{output_path}/{rn_layer_node.layer}")
    filepath = output_dir / name.lstrip("/")
    render_product_main_beauty = f"{filepath}_{rn_layer_node.layer}{aov_sep}beauty.####"

    output.base_path = render_product_main_beauty if multi_exr else str(output_path)

    slots.clear()

    aov_file_products = {}

    old_links = {
        link.from_socket.name: link for link in tree.links
        if link.to_node == old_output_node}

    # Create a new socket for the beauty output
    pass_name = "rgba" if multi_exr else "beauty"
    for render_layer_node in render_aovs_dict.keys():
        render_layer = render_layer_node.layer
        slot, _ = _create_aov_slot(
            name, aov_sep, slots, pass_name, multi_exr, output_path, render_layer)
        tree.links.new(render_layer_node.outputs["Image"], slot)

    if compositing:
        # Create a new socket for the composite output
        # with only the one view layer
        pass_name = "composite"
        if rn_layer_node:
            render_layer = rn_layer_node.layer
            aov_file_products[render_layer] = []
            comp_socket, filepath = _create_aov_slot(
                name, aov_sep, slots, pass_name, multi_exr, output_path, render_layer)
            aov_file_products[render_layer].append((pass_name, filepath))
            # If there's a composite node, we connect its input with the new output
            if composite_node:
                for link in tree.links:
                    if link.to_node == composite_node:
                        tree.links.new(link.from_socket, comp_socket)
                        break

        # For each active render pass, we add a new socket to the output node
        # and link it
        for render_layer_node, passes in render_aovs_dict.items():
            render_layer = render_layer_node.layer
            if not aov_file_products.get(render_layer, []):
                aov_file_products[render_layer] = []
            for rpass in passes:
                slot, filepath = _create_aov_slot(
                    name, aov_sep, slots, rpass.name, multi_exr, output_path, render_layer)

                aov_file_products[render_layer].append((rpass.name, filepath))

                # If the rpass was not connected with the old output node, we connect
                # it with the new one.
                if not old_links.get(rpass.name):
                    tree.links.new(rpass, slot)

        for link in list(old_links.values()):
            # Check if the socket is still available in the new output node.
            socket = output.inputs.get(link.to_socket.name)
            # If it is, we connect it with the new output node.
            if socket:
                tree.links.new(link.from_socket, socket)
            # Then, we remove the old link.
            tree.links.remove(link)

    if old_output_node:
        output.location = old_output_node.location
        tree.nodes.remove(old_output_node)

    output.name = "AYON File Output"
    output.label = "AYON File Output"

    return {} if multi_exr else aov_file_products


def imprint_render_settings(node, data):
    RENDER_DATA = "render_data"
    if not node.get(RENDER_DATA):
        node[RENDER_DATA] = {}
    for key, value in data.items():
        if value is None:
            continue
        node[RENDER_DATA][key] = value



def create_node_with_new_view_layers(tree, comp_layer_type, view_layers, render_layer_nodes):
    for view_layer in view_layers:
        render_layer_node = tree.nodes.new(comp_layer_type)
        render_layer_node.layer = view_layer.name
        render_layer_nodes.add(render_layer_node)
    return render_layer_nodes


def prepare_rendering(asset_group):
    name = asset_group.name

    filepath = Path(bpy.data.filepath)
    assert filepath, "Workfile not saved. Please save the file first."

    dirpath = filepath.parent
    file_name = Path(filepath.name).stem

    project = get_current_project_name()
    settings = get_project_settings(project)

    render_folder = get_default_render_folder(settings)
    aov_sep = get_aov_separator(settings)
    ext = get_image_format(settings)
    multilayer = get_multilayer(settings)
    renderer = get_renderer(settings)
    compositing = get_compositing(settings)

    set_render_format(ext, multilayer)
    bpy.context.scene.render.engine = renderer
    view_layers = bpy.context.scene.view_layers
    aov_list, custom_passes = set_render_passes(settings, renderer, view_layers)

    output_path = Path.joinpath(dirpath, render_folder, file_name)

    render_product = get_render_product(output_path, name, aov_sep, view_layers)
    aov_file_product = set_node_tree(
        output_path, name, aov_sep, ext,
        multilayer, compositing, view_layers
    )

    # Clear the render filepath, so that the output is handled only by the
    # output node in the compositor.
    tmp_render_path = os.path.join(tempfile.gettempdir(), "renders", "tmp")
    tmp_render_path = tmp_render_path.replace("\\", "/")
    bpy.context.scene.render.filepath = f"{tmp_render_path}/"
    render_settings = {
        "render_folder": render_folder,
        "aov_separator": aov_sep,
        "image_format": ext,
        "multilayer_exr": multilayer,
        "aov_list": aov_list,
        "custom_passes": custom_passes,
        "render_product": render_product,
        "aov_file_product": aov_file_product,
        "review": True,
    }

    imprint_render_settings(asset_group, render_settings)


def update_render_product(name, output_path, render_product):
    tmp_render_product = {}
    render_layers = bpy.context.scene.view_layers
    project = get_current_project_name()
    settings = get_project_settings(project)
    aov_sep = get_aov_separator(settings)
    for render_layer in render_layers:
        rl_name = render_layer.name
        tmp_render_product[rl_name] = []
        rn_product = render_product[rl_name]
        for rpass_name, _ in rn_product:
            filename = f"{rl_name}/{name}_{rl_name}{aov_sep}{rpass_name}.####"
            filepath = str(output_path / filename.lstrip("/"))
            tmp_render_product[rl_name].append((rpass_name, filepath))

    return tmp_render_product
