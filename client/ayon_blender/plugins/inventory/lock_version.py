from __future__ import annotations

from typing import Any

from ayon_core.pipeline import InventoryAction

from ayon_blender.api.constants import AYON_PROPERTY
from ayon_blender.api.pipeline import metadata_update


class LockVersions(InventoryAction):
    label = "Lock versions"
    icon = "lock"
    color = "#ffffff"
    order = -1

    @staticmethod
    def is_compatible(container: dict[str, Any]) -> bool:
        return container.get("version_locked") is not True

    def process(self, containers: list[dict[str, Any]]) -> bool:
        for container in containers:
            if container.get("version_locked") is True:
                continue
            metadata_update(container["node"], {"version_locked": True})
        return True


class UnlockVersions(InventoryAction):
    label = "Unlock versions"
    icon = "lock-open"
    color = "#ffffff"
    order = -1

    @staticmethod
    def is_compatible(container: dict[str, Any]) -> bool:
        return container.get("version_locked") is True

    def process(self, containers: list[dict[str, Any]]) -> bool:
        for container in containers:
            if container.get("version_locked") is not True:
                continue
            metadata = container["node"].get(AYON_PROPERTY)
            if metadata and "version_locked" in metadata:
                del metadata["version_locked"]
        return True
