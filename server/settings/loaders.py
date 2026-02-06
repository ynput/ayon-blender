from ayon_server.settings import BaseSettingsModel, SettingsField


class BlendLinkLoaderFlatModel(BaseSettingsModel):
    instance_collections: bool = SettingsField(
        False,
        title="Instances Collection",
        description=(
            "Create instances for collections, "
            "rather than adding them directly to the scene."
        ),
    )
    instance_object_data: bool = SettingsField(
        False,
        title="Instance Object Data",
        description=(
            "Create instances for object data which "
            "are not referenced by any objects"
        ),
    )


class BlendLoaderModel(BaseSettingsModel):
    create_animation_instance_on_load: bool = SettingsField(
        True,
        title="Create Animation Instance on Load",
        description=(
            "Automatically create an animation instance when loading rig files."
        ),
    )


class CacheLoaderModel(BaseSettingsModel):
    always_add_cache_reader: bool = SettingsField(
        False,
        title="Always Add Cache Reader (Alembic)",
        description=(
            "Always add a cache reader when importing Alembic files."
        ),
    )


class LoadersModel(BaseSettingsModel):
    AbcCameraLoader: CacheLoaderModel = SettingsField(
        default_factory=CacheLoaderModel,
        title="Alembic Camera Loader"
    )
    BlendLinkLoaderFlat: BlendLinkLoaderFlatModel = SettingsField(
        default_factory=BlendLinkLoaderFlatModel,
        title="Link Blend (Flat)"
    )
    BlendLoader: BlendLoaderModel = SettingsField(
        default_factory=BlendLoaderModel,
        title="Reference Loader"
    )
    CacheModelLoader: CacheLoaderModel = SettingsField(
        default_factory=CacheLoaderModel,
        title="Cache Model Loader"
    )


DEFAULT_LOADERS_SETTINGS = {
    "AbcCameraLoader": {
        "always_add_cache_reader": False
    },
    "BlendLinkLoaderFlat": {
        "instance_collections": False,
        "instance_object_data": False
    },
    "BlendLoader": {
        "create_animation_instance_on_load": True
    },
    "CacheModelLoader": {
        "always_add_cache_reader": False
    }
}
