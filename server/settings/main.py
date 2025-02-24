from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    TemplateWorkfileBaseOptions,
    task_types_enum,
)
from .imageio import BlenderImageIOModel
from .publish_plugins import (
    PublishPluginsModel,
    DEFAULT_BLENDER_PUBLISH_SETTINGS
)
from .render_settings import (
    RenderSettingsModel,
    DEFAULT_RENDER_SETTINGS
)


class UnitScaleSettingsModel(BaseSettingsModel):
    enabled: bool = SettingsField(True, title="Enabled")
    apply_on_opening: bool = SettingsField(
        False, title="Apply on Opening Existing Files")
    base_file_unit_scale: float = SettingsField(
        1.0, title="Base File Unit Scale",
             description="Typically increments in tenths, e.g. 0.1, 0.01 or 100.",    
    )


class IncludeHandlesProfilesModel(BaseSettingsModel):
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task Types",
        description="Filter by task types",
        enum_resolver=task_types_enum,
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task Names",
        description="Filter by task names.",
    )
    include_handles: bool = SettingsField(True, title="Include handles")


class IncludeHandlesModel(BaseSettingsModel):
    include_handles_default: bool = SettingsField(False, 
        title="Include handles by default",
        description="The total frame range is extended by frame handles.",
    )
    profiles: list[IncludeHandlesProfilesModel] = SettingsField(
        default_factory=list,
        title="Include/exclude handles by profiles",
        description="The total frame range is extended by frame handles.",
    )


class BlenderSettings(BaseSettingsModel):
    unit_scale_settings: UnitScaleSettingsModel = SettingsField(
        default_factory=UnitScaleSettingsModel,
        title="Set Unit Scale",
        description="Sets your preferred world scale ratio - mostly when importing from other apps.",
    )
    set_resolution_startup: bool = SettingsField(
        True,
        title="Set Resolution on Startup",
        description="Forces values from AYON project on the launch.",
    )
    set_frames_startup: bool = SettingsField(
        True,
        title="Set Start/End Frames and FPS on Startup",
        description="Forces values from AYON project on the launch.",
    )
    include_handles: IncludeHandlesModel = SettingsField(
        default_factory=IncludeHandlesModel,
        title="Include/Exclude Handles in default playback & render range",
        description="You can disable using handles while still have them configured in AYON project.",
    )
    imageio: BlenderImageIOModel = SettingsField(
        default_factory=BlenderImageIOModel,
        title="Color Management (ImageIO)",
        description="Enable / disable global color management system using OCIO files.",
    )
    RenderSettings: RenderSettingsModel = SettingsField(
        default_factory=RenderSettingsModel, title="Render Settings")
    workfile_builder: TemplateWorkfileBaseOptions = SettingsField(
        default_factory=TemplateWorkfileBaseOptions,
        title="Workfile Builder",
        description="Configures startup workfile blend scene.",
    )
    publish: PublishPluginsModel = SettingsField(
        default_factory=PublishPluginsModel,
        title="Publish Plugins",
        description="Configure various validator and extractor types for publishing.",
    )


DEFAULT_VALUES = {
    "unit_scale_settings": {
        "enabled": True,
        "apply_on_opening": False,
        "base_file_unit_scale": 1.00
    },
    "set_frames_startup": True,
    "set_resolution_startup": True,
    "include_handles": {
        "include_handles_default": False,
        "profiles": []
    },
    "RenderSettings": DEFAULT_RENDER_SETTINGS,
    "publish": DEFAULT_BLENDER_PUBLISH_SETTINGS,
    "workfile_builder": {
        "create_first_version": False,
        "custom_templates": []
    }
}
