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


class ShadingSetting(BaseSettingsModel):
    _layout = "expanded"
    type: str = SettingsField(
        "MATERIAL",
        title="Shading Type",
        enum_resolver=get_shading_type_enum
    )


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
                    "color_depth": "8",
                    "compression": 15
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
