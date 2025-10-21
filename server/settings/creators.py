import re
from pydantic import validator

from ayon_server.exceptions import BadRequestException
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
)


class BasicCreatorModel(BaseSettingsModel):
    enabled: bool = SettingsField(
        True,
        title="Enabled"
    )
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Variants"
    )

    @staticmethod
    def is_valid_variant(variant: str) -> bool:
        return re.fullmatch(r'[A-Za-z0-9_]+', variant)  # alphanumeric

    @validator("default_variants")
    def valid_variants(cls, value):
        for variant in value:
            if not cls.is_valid_variant(variant):
                raise BadRequestException(
                    f"Invalid characters in variant name {variant}. "
                    "Allowed characters are A-Za-z0-9_"
                )
        return value





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
    CreatePointcache: BasicCreatorModel = SettingsField(
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
    "CreatePointcache": {"default_variants": ["Main"], "enabled": True},
    "CreateRender": {"default_variants": ["Main"], "enabled": True},
    "CreateReview": {"default_variants": ["Main"], "enabled": True},
    "CreateRig": {"default_variants": ["Main"], "enabled": True},
    "CreateUSD": {"default_variants": ["Main"], "enabled": True},
}
