import json
from pydantic import validator
from ayon_server.exceptions import BadRequestException
from ayon_server.settings import BaseSettingsModel, SettingsField


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
            "Environment's can't be parsed as json object"
        )
    return value


class ValidatePluginModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")


class ValidateFileSavedModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="ValidateFileSaved")
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    exclude_families: list[str] = SettingsField(
        default_factory=list,
        title="Exclude product types"
    )


class ExtractBlendModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    families: list[str] = SettingsField(
        default_factory=list,
        title="Families"
    )
    compress: bool = SettingsField(True, title="Compress")


class ExtractBlendAnimationModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    compress: bool = SettingsField(False, title="Compress")


class ExtractPlayblastModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    optional: bool = SettingsField(title="Optional")
    active: bool = SettingsField(title="Active")
    presets: str = SettingsField("", title="Presets", widget="textarea")
    compress: bool = SettingsField(False, title="Compress")

    @validator("presets")
    def validate_json(cls, value):
        return validate_json_dict(value)


class PublishPluginsModel(BaseSettingsModel):
    ValidateAbsoluteDataBlockPaths: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Absolute Data Block Paths",
        description="Checks if external data having absolute file path.",
        section="General Validators"
    )
    ValidateCameraZeroKeyframe: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Camera Zero Keyframe",
        description="Checks if a keyframe is set on frame zero - mostly used when loading in Unreal Engine shifting the first keyframe to zero.",
    )
    ValidateFileSaved: ValidateFileSavedModel = SettingsField(
        default_factory=ValidateFileSavedModel,
        title="Validate File Saved",
        description="Checks if workfile changes have been saved, forcing user to perform save action if not.",
    )
    ValidateInstanceEmpty: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Instance is not Empty",
        description="Checks for empty publish instances which could result in no data when published.",
    )
    ValidateMeshHasUvs: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Mesh Has Uvs",
        description="Checks for geometry having UV set defined.",
        section="Model Validators"
    )
    ValidateMeshNoNegativeScale: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Mesh No Negative Scale",
        description="Checks for object scaling in negative values which is prohibited then.",
    )
    ValidateModelMeshUvMap1: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Model Mesh Has UV map named map1",
        description="Checks if objects have a UV set named 'map1' meeting Maya standards.",
    )
    ValidateTransformZero: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Transform Zero",
        description="Checks all objects transforms are zero values.",
    )
    ValidateNoColonsInName: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate No Colons In Name",
        description="Checks for invalid naming format containing `:` within name - mostly when exporting to Unreal Engine.",
    )
    ValidateRenderCameraIsSet: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Render Camera Is Set",
        description="Checks for renderable camera when using Render.",
        section="Render Validators"
    )
    ValidateDeadlinePublish: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Render Output for Deadline",
        description="Checks render output folder naming and if matching workfile and version.",
    )
    ValidateFrameRange: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Validate Frame Range",
        description="Checks if scene frame range matches AYON project values for the context.",
    )
    ExtractBlend: ExtractBlendModel = SettingsField(
        default_factory=ExtractBlendModel,
        title="Extract Blend",
        section="Extractors"
    )
    ExtractFBX: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Extract FBX"
    )
    ExtractModelABC: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Extract ABC"
    )
    ExtractBlendAnimation: ExtractBlendAnimationModel = SettingsField(
        default_factory=ExtractBlendAnimationModel,
        title="Extract Blend Animation"
    )
    ExtractAnimationFBX: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Extract Animation FBX"
    )
    ExtractCamera: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Extract Camera"
    )
    ExtractCameraABC: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Extract Camera as ABC"
    )
    ExtractLayout: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Extract Layout (JSON)"
    )
    ExtractThumbnail: ExtractPlayblastModel = SettingsField(
        default_factory=ExtractPlayblastModel,
        title="Extract Thumbnail"
    )
    ExtractPlayblast: ExtractPlayblastModel = SettingsField(
        default_factory=ExtractPlayblastModel,
        title="Extract Playblast"
    )
    ExtractModelUSD: ValidatePluginModel = SettingsField(
        default_factory=ValidatePluginModel,
        title="Extract Model USD"
    )


DEFAULT_BLENDER_PUBLISH_SETTINGS = {
    "ValidateAbsoluteDataBlockPaths": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateCameraZeroKeyframe": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateFileSaved": {
        "enabled": True,
        "optional": False,
        "active": True,
        "exclude_families": []
    },
    "ValidateRenderCameraIsSet": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateDeadlinePublish": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateMeshHasUvs": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ValidateMeshNoNegativeScale": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateModelMeshUvMap1": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateTransformZero": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateNoColonsInName": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ValidateInstanceEmpty": {
        "enabled": True,
        "optional": False,
        "active": True
    },
    "ValidateFrameRange": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ExtractBlend": {
        "enabled": True,
        "optional": True,
        "active": True,
        "families": [
            "model",
            "camera",
            "rig",
            "action",
            "layout",
            "blendScene"
        ],
        "compress": False
    },
    "ExtractFBX": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ExtractModelABC": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ExtractBlendAnimation": {
        "enabled": True,
        "optional": True,
        "active": True,
        "compress": False
    },
    "ExtractAnimationFBX": {
        "enabled": False,
        "optional": True,
        "active": True
    },
    "ExtractCamera": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ExtractCameraABC": {
        "enabled": True,
        "optional": True,
        "active": True
    },
    "ExtractLayout": {
        "enabled": True,
        "optional": True,
        "active": False
    },
    "ExtractThumbnail": {
        "enabled": True,
        "optional": True,
        "active": True,
        "presets": json.dumps(
            {
                "model": {
                    "image_settings": {
                        "file_format": "JPEG",
                        "color_mode": "RGB",
                        "quality": 100
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
                        "file_format": "JPEG",
                        "color_mode": "RGB",
                        "quality": 100
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
        )
    },
    "ExtractPlayblast": {
        "enabled": True,
        "optional": True,
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
        )
    },
    "ExtractModelUSD": {
        "enabled": True,
        "optional": True,
        "active": True
    }
}
