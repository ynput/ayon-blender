from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
)


class BasicCreatorModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Variants"
    )


class CreatorsModel(BaseSettingsModel):

    CreateAction: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Action"
    )
    CreateAnimation: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Animation"
    )
    CreateBlendScene: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create BlendScene"
    )
    CreateCamera: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Camera"
    )
    CreateLayout: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Layout"
    )
    CreateModel: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Model"
    )
    CreatePointCache: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Point Cache"
    )
    CreateRender: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Render"
    )
    CreateReview: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Review"
    )
    CreateRig: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Rig"
    )
    CreateUSD: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create USD"
    )


DEFAULT_CREATORS_SETTINGS = {
    "CreateAction": {"default_variants": ["Main"], "enabled": True},
    "CreateAnimation": {"default_variants": ["Main"], "enabled": True},
    "CreateBlendScene": {"default_variants": ["Main"], "enabled": True},
    "CreateCamera": {"default_variants": ["Main"], "enabled": True},
    "CreateLayout": {"default_variants": ["Main"], "enabled": True},
    "CreateModel": {"default_variants": ["Main"], "enabled": True},
    "CreatePointCache": {"default_variants": ["Main"], "enabled": True},
    "CreateRender": {"default_variants": ["Main"], "enabled": True},
    "CreateRender": {"default_variants": ["Main"], "enabled": True},
    "CreateReview": {"default_variants": ["Main"], "enabled": True},
    "CreateRig": {"default_variants": ["Main"], "enabled": True},
    "CreateUSD": {"default_variants": ["Main"], "enabled": True},
}
