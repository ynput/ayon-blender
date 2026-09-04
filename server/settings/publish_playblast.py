import json
from ayon_server.exceptions import BadRequestException
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    task_types_enum,
)
from pydantic import validator


def validate_json_dict(value):
    if not value.strip():
        return "{}"
    try:
        converted_value = json.loads(value)
        success = isinstance(converted_value, dict)
    except json.JSONDecodeError:
        success = False

    if not success:
        raise BadRequestException(
            "Presets can't be parsed as a JSON object"
        )
    return value


def get_color_depth_enum():
    return [
        {"label": "8", "value": "8"},
        {"label": "16", "value": "16"},
        {"label": "32", "value": "32"},
    ]


def get_shading_type_enum():
    return [
        {"label": "Material", "value": "MATERIAL"},
        {"label": "Solid", "value": "SOLID"},
        {"label": "Wireframe", "value": "WIREFRAME"},
        {"label": "Rendered", "value": "RENDERED"},
    ]


def get_shading_light_enum():
    return [
        {"label": "Studio", "value": "STUDIO"},
        {"label": "Flat", "value": "FLAT"},
        {"label": "Matcap", "value": "MATCAP"},
    ]


def get_color_type_enum():
    return [
        {"label": "Material", "value": "MATERIAL"},
        {"label": "Object", "value": "OBJECT"},
        {"label": "Random", "value": "RANDOM"},
        {"label": "Vertex", "value": "VERTEX"},
        {"label": "Texture", "value": "TEXTURE"},
        {"label": "Single", "value": "SINGLE"},
    ]


class ImageSetting(BaseSettingsModel):
    _layout = "expanded"
    file_format: str = SettingsField("png", title="File Format")
    color_mode: str = SettingsField("RGB", title="Color Mode")
    color_depth: str = SettingsField(
        "8",
        title="Color Depth",
        enum_resolver=get_color_depth_enum
    )
    compression: int = SettingsField(15, title="Compression")


class OverlaySetting(BaseSettingsModel):
    _layout = "expanded"
    show_overlays: bool = SettingsField(False, title="Show Overlays")
    show_ortho_grid: bool = SettingsField(False, title="Show Ortho Grid")
    show_floor: bool = SettingsField(False, title="Show Floor")
    show_axis_x: bool = SettingsField(False, title="Show X Axis")
    show_axis_y: bool = SettingsField(False, title="Show Y Axis")
    show_axis_z: bool = SettingsField(False, title="Show Z Axis")
    show_text: bool = SettingsField(False, title="Show Overlay Text")
    show_stats: bool = SettingsField(False, title="Show Scene Stats")
    show_cursor: bool = SettingsField(False, title="Show 3D Cursor")
    show_annotation: bool = SettingsField(True, title="Show Annotations")
    show_extras: bool = SettingsField(True, title="Show Extras Object details")
    show_relationship_lines: bool = SettingsField(False, title="Show Relationship Lines")
    show_outline_selected: bool = SettingsField(False, title="Show Outline Selected ")
    show_motion_paths: bool = SettingsField(False, title="Show Motion Paths")
    show_object_origins: bool = SettingsField(False, title="Show Object Origins")
    show_bones: bool = SettingsField(False, title="Show Bones")


class ShadingSetting(BaseSettingsModel):
    _layout = "expanded"
    light: str = SettingsField(
        "STUDIO",
        title="Light",
        enum_resolver=get_shading_light_enum
    )
    type: str = SettingsField(
        "MATERIAL",
        title="Shading Type",
        enum_resolver=get_shading_type_enum
    )
    color_type: str = SettingsField(
        "MATERIAL",
        title="Color Type",
        enum_resolver=get_color_type_enum
    )
    show_xray: bool = SettingsField(False, title="Show X-Ray")
    show_shadows: bool = SettingsField(False, title="Show Shadows")
    show_cavity: bool = SettingsField(False, title="Show Cavity")


class DisplayOptionsSetting(BaseSettingsModel):
    _layout = "expanded"
    shading: ShadingSetting = SettingsField(
        default_factory=ShadingSetting,
        title="Shading Options"
    )
    overlay: OverlaySetting = SettingsField(
        default_factory=OverlaySetting,
        title="Overlay Options"
    )
    show_gizmo: bool = SettingsField(False, title="Show Gizmo")


class ResolutionSetting(BaseSettingsModel):
    _layout = "expanded"
    width: int = SettingsField(1920, title="Width")
    height: int = SettingsField(1080, title="Height")
    maintain_aspect_ratio: bool = SettingsField(True, title="Maintain Aspect Ratio")


class CameraOptionsSetting(BaseSettingsModel):
    background_images: bool = SettingsField(False, title="Show Background Images")


class CapturePresetSetting(BaseSettingsModel):
    image_settings: ImageSetting = SettingsField(
        default_factory=ImageSetting,
        title="Image Compression Settings",
        section="Image Compression Settings")
    resolution: ResolutionSetting = SettingsField(
        default_factory=ResolutionSetting,
        title="Resolution Settings",
        section="Resolution Settings"
    )
    display_options: DisplayOptionsSetting = SettingsField(
        default_factory=DisplayOptionsSetting,
        title="Display Options",
        section="Display Options")
    camera_options: CameraOptionsSetting = SettingsField(
        default_factory=CameraOptionsSetting,
        title="Camera Options",
        section="Camera Options"
    )
    additional_presets: str = SettingsField(
        "{}", title="Additional Presets",
        widget="textarea"
    )

    @validator("additional_presets")
    def validate_json(cls, value):
        if not value.strip():
            return "{}"
        try:
            converted_value = json.loads(value)
            success = isinstance(converted_value, dict)
        except json.JSONDecodeError:
            success = False

        if not success:
            raise BadRequestException(
                "The attibutes can't be parsed as json object"
            )
        return value


class PlayblastProfilesModel(BaseSettingsModel):
    _layout = "expanded"
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list, title="Task names"
    )
    product_names: list[str] = SettingsField(
        default_factory=list, title="Products names"
    )
    product_base_types: list[str] = SettingsField(
        default_factory=list, title="Product Base Types"
    )
    presets: CapturePresetSetting = SettingsField(
        default_factory=CapturePresetSetting,
        title="Capture Preset"
    )


class ExtractPlayblastModel(BaseSettingsModel):
    enabled: bool = SettingsField(True, title="Enabled")
    optional: bool = SettingsField(True, title="Optional")
    active: bool = SettingsField(True, title="Active")
    presets: str = SettingsField(
        "", title="DEPRECATED! Please use \"Profiles\" below. Presets",
        widget="textarea"
    )
    profiles: list[PlayblastProfilesModel] = SettingsField(
        default_factory=list,
        title="Profiles"
    )

    @validator("presets")
    def validate_json(cls, value):
        return validate_json_dict(value)



DEFAULT_PLAYBLAST_SETTING = {
    "enabled": True,
    "optional": False,
    "active": True,
    "presets": json.dumps(
        {
            "default": {
                "image_settings": {
                    "file_format": "PNG",
                    "color_mode": "RGB",

                },
                "display_options": {
                    "shading": {
                        "type": "MATERIAL",
                        "render_pass": "COMBINED"
                    },
                    "overlay": {
                        "show_overlays": False
                    }
                }
            }
        },
        indent=4
        ),
    "profiles": []
}


DEFAULT_THUMBNAIL_SETTING = {
    "enabled": True,
    "optional": True,
    "active": True,
    "presets": json.dumps(
        {
            "model": {
                "image_settings": {
                    "file_format": "PNG",
                    "color_mode": "RGB"
                },
                "display_options": {
                    "shading": {
                        "light": "STUDIO",
                        "studio_light": "Default",
                        "type": "SOLID",
                        "color_type": "OBJECT",
                        "show_xray": False,
                        "show_shadows": False,
                        "show_cavity": True
                    },
                    "overlay": {
                        "show_overlays": False
                    }
                }
            },
            "rig": {
                "image_settings": {
                    "file_format": "PNG",
                    "color_mode": "RGB"
                },
                "display_options": {
                    "shading": {
                        "light": "STUDIO",
                        "studio_light": "Default",
                        "type": "SOLID",
                        "color_type": "OBJECT",
                        "show_xray": True,
                        "show_shadows": False,
                        "show_cavity": False
                    },
                    "overlay": {
                        "show_overlays": True,
                        "show_ortho_grid": False,
                        "show_floor": False,
                        "show_axis_x": False,
                        "show_axis_y": False,
                        "show_axis_z": False,
                        "show_text": False,
                        "show_stats": False,
                        "show_cursor": False,
                        "show_annotation": False,
                        "show_extras": False,
                        "show_relationship_lines": False,
                        "show_outline_selected": False,
                        "show_motion_paths": False,
                        "show_object_origins": False,
                        "show_bones": True
                    }
                }
            }
        },
        indent=4,
    ),
    "profiles": [
        {
            "task_types": [],
            "task_names": [],
            "product_names": [],
            "product_base_types": ["model"],
            "presets": {
                "image_settings": {
                    "file_format": "PNG",
                    "color_mode": "RGB",
                    "color_depth": "8",
                    "compression": 15
                },
                "resolution": {
                    "width": 1920,
                    "height": 1080,
                    "maintain_aspect_ratio": True
                },
                "display_options": {
                    "shading": {
                        "light": "STUDIO",
                        "studio_light": "Default",
                        "type": "SOLID",
                        "color_type": "OBJECT",
                        "show_xray": False,
                        "show_shadows": False,
                        "show_cavity": True
                    },
                    "overlay": {
                        "show_overlays": False,
                        "show_ortho_grid": False,
                        "show_floor": False,
                        "show_axis_x": False,
                        "show_axis_y": False,
                        "show_axis_z": False,
                        "show_text": False,
                        "show_stats": False,
                        "show_cursor": False,
                        "show_annotation": False,
                        "show_extras": False,
                        "show_relationship_lines": False,
                        "show_outline_selected": False,
                        "show_motion_paths": False,
                        "show_object_origins": False,
                        "show_bones": False
                    }
                },
                "additional_presets": "{}",
            },
        },
        {
            "task_types": [],
            "task_names": [],
            "product_names": [],
            "product_base_types": ["rig"],
            "presets": {
                "image_settings": {
                    "file_format": "PNG",
                    "color_mode": "RGB",
                    "color_depth": "8",
                    "compression": 15
                },
                "resolution": {
                    "width": 1920,
                    "height": 1080,
                    "maintain_aspect_ratio": True
                },
                "display_options": {
                    "shading": {
                        "light": "STUDIO",
                        "studio_light": "Default",
                        "type": "SOLID",
                        "color_type": "OBJECT",
                        "show_xray": True,
                        "show_shadows": False,
                        "show_cavity": True
                    },
                    "overlay": {
                        "show_overlays": True,
                        "show_ortho_grid": False,
                        "show_floor": False,
                        "show_axis_x": False,
                        "show_axis_y": False,
                        "show_axis_z": False,
                        "show_text": False,
                        "show_stats": False,
                        "show_cursor": False,
                        "show_annotation": False,
                        "show_extras": False,
                        "show_relationship_lines": False,
                        "show_outline_selected": False,
                        "show_motion_paths": False,
                        "show_object_origins": False,
                        "show_bones": True
                    }
                },
                "additional_presets": "{}",
            },
        }
    ]
}
