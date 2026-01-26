from ayon_server.settings import BaseSettingsModel, SettingsField


class BlendLinkLoader(BaseSettingsModel):
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

class LoadersModel(BaseSettingsModel):
    BlendLoader: BlendLoaderModel = SettingsField(
        default_factory=BlendLoaderModel,
        title="Reference Loader"
    )


DEFAULT_LOADERS_SETTINGS = {
    "BlendLinkLoader": {
        "instance_collections": False,
        "instance_object_data": False
    },
    "BlendLoader": {
        "create_animation_instance_on_load": True
    }
}
