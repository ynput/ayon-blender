from pydantic import validator
from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.settings.validators import ensure_unique_names


class ImageIOFileRuleModel(BaseSettingsModel):
    name: str = SettingsField("", title="Rule name")
    pattern: str = SettingsField("", title="Regex pattern")
    colorspace: str = SettingsField("", title="Colorspace name")
    ext: str = SettingsField("", title="File extension")


class ImageIOFileRulesModel(BaseSettingsModel):
    activate_host_rules: bool = SettingsField(False)
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list,
        title="Rules"
    )

    @validator("rules")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class WorkfileImageIOModel(BaseSettingsModel):
    """Set the scene color management on new workfiles.

    Existing workfiles are only changed on opening when enabled.
    Empty text values are left as they are in the workfile. Exposure and
    gamma are always set."""

    enabled: bool = SettingsField(False, title="Enabled")
    apply_on_opening: bool = SettingsField(
        False, title="Apply on Opening Existing Files")
    display: str = SettingsField(
        "",
        title="Display",
        description="OCIO display, e.g. 'sRGB - Display'.",
    )
    view: str = SettingsField(
        "",
        title="View",
        description="OCIO view of the display, e.g. 'ACES 1.0 - SDR Video'.",
    )
    look: str = SettingsField(
        "",
        title="Look",
        description="OCIO look of the view, or 'None' to disable the look.",
    )
    exposure: float = SettingsField(
        0.0,
        title="Exposure",
        description="Exposure of the view in stops. Blender's default is 0.0.",
    )
    gamma: float = SettingsField(
        1.0,
        title="Gamma",
        description="Gamma of the view. Blender's default is 1.0.",
    )
    working_space: str = SettingsField(
        "",
        title="Working Space",
        description=(
            "Blender 5.0+ only. Scene linear working color space of the"
            " blend file, e.g. 'ACEScg'. Blender only accepts colorspaces of"
            " the OCIO config that match Linear Rec.709, Linear Rec.2020 or"
            " ACEScg. Colors in the blend file are converted on change."
        ),
    )
    sequencer_colorspace: str = SettingsField(
        "",
        title="Sequencer Colorspace",
        description="Colorspace the Video Sequencer works in, e.g. 'ACEScg'.",
    )


class BlenderImageIOModel(BaseSettingsModel):
    activate_host_color_management: bool = SettingsField(
        True, title="Enable Color Management",
        description="When enabled, Blender follows global color management using OCIO files set in ayon-core.",
    )
    file_rules: ImageIOFileRulesModel = SettingsField(
        default_factory=ImageIOFileRulesModel,
        title="File Rules"
    )
    workfile: WorkfileImageIOModel = SettingsField(
        default_factory=WorkfileImageIOModel,
        title="Workfile"
    )
