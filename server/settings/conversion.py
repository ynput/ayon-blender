import json
from typing import Any
from semver import VersionInfo


def _parse_legacy_preset(raw_preset: Any) -> dict[str, Any]:
    if raw_preset is None:
        return {}

    if isinstance(raw_preset, str):
        try:
            parsed = json.loads(raw_preset)
        except (TypeError, ValueError):
            return {}
    else:
        parsed = raw_preset

    if isinstance(parsed, dict):
        return parsed

    return {}


def _convert_thumbnail_settings_model_1_1_8(
        overrides: dict[str, Any], version: VersionInfo) -> None:
    # Implement the conversion logic for thumbnail settings from version 0.4.11
    if (version.major, version.minor, version.patch) > (1, 1, 8):
        return

    publish_settings = overrides.setdefault("publish", {})
    extract_thumbnail_settings = publish_settings.setdefault(
        "ExtractThumbnail", {}
    )
    capture_presets = extract_thumbnail_settings.get("presets", "{}")
    parsed_presets = _parse_legacy_preset(capture_presets)
    if not parsed_presets:
        return

    if extract_thumbnail_settings.get("profiles"):
        return

    extract_thumbnail_settings["profiles"] = []
    for product_base_type in parsed_presets.keys():
        extract_thumbnail_settings["profiles"].append(
            {
                "task_types": [],
                "task_names": [],
                "product_names": [],
                "product_base_types": [product_base_type],
                "presets": {
                    **(parsed_presets.get(product_base_type) or {}),
                    "additional_presets": "{}",
                },
            }
        )

    return overrides


def _convert_playblast_settings_model_1_1_8(
        overrides: dict[str, Any], version: VersionInfo) -> None:
    # Implement the conversion logic for playblast settings from version 0.4.11
    if (version.major, version.minor, version.patch) > (1, 1, 8):
        return

    publish_settings = overrides.setdefault("publish", {})
    extract_playblast_settings = publish_settings.setdefault(
        "ExtractPlayblast", {}
    )
    capture_presets = extract_playblast_settings.get("presets", "{}")
    parsed_presets = _parse_legacy_preset(capture_presets)
    if not parsed_presets:
        return

    if extract_playblast_settings.get("profiles"):
        return

    extract_playblast_settings["profiles"] = [{
        "task_types": [],
        "task_names": [],
        "product_names": [],
        "product_base_types": [],
        "presets": {
            **(parsed_presets.get("default") or {}),
            "additional_presets": "{}",
        },
    }]

    return overrides


def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    version = VersionInfo.parse(source_version)
    _convert_playblast_settings_model_1_1_8(overrides, version)
    _convert_thumbnail_settings_model_1_1_8(overrides, version)
    return overrides
