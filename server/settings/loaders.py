from ayon_server.settings import BaseSettingsModel, SettingsField


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
    "BlendLoader": {
        "create_animation_instance_on_load": True
    }
}
