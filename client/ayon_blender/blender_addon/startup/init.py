try:
    from ayon_core.pipeline import install_host
    from ayon_blender.api import BlenderHost
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        f"{exc}. This usually happens if Blender is launched without the "
        "--python-use-system-env argument. Make sure you have the Blender "
        "application 'Arguments' configured correctly so that Blender has "
        "access to the launched context's PYTHONPATH."
    ) from exc

def register():
    install_host(BlenderHost())


def unregister():
    pass
