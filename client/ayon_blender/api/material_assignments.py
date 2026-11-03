"""Preserve local material slot assignments when a container is updated.

Loading a published file **by appending it** (e.g. 'Append Blend' or 'Load
FBX') re-creates the objects from the representation on every update. The
artists' locally assigned materials are lost in the process because the newly
appended objects only carry the materials that were published in the new
version. See https://github.com/ynput/ayon-blender/issues/109

The loaders use the helpers in this module to:

1. record the material slot layout of a freshly loaded container, the
   *baseline*, and store it along the container metadata;
2. on update, compare the current layout to that baseline and keep only the
   slots that were changed locally, the *overrides*;
3. apply those overrides back onto the objects of the newly loaded version.

Keeping only the changed slots means slots that the artist never touched keep
following the published file, so material changes coming from a new version
still come through.

An empty slot is represented by an empty string, because Blender's ID
properties cannot store `None` values.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

import bpy

log = logging.getLogger(__name__)


def get_material_layout(
    objects: Iterable[bpy.types.Object],
) -> Dict[str, list]:
    """Return the material slot layout of the given objects.

    Arguments:
        objects (Iterable[bpy.types.Object]): Objects to get the layout of.

    Returns:
        Dict[str, list]: Object name mapped to its material slots ordered by
            slot index. Every slot is a dict with the `material` name (empty
            string for an empty slot) and the `link` type (`DATA` or
            `OBJECT`). Objects that don't support materials are skipped.
    """
    layout: Dict[str, list] = {}
    for obj in objects:
        if not _supports_materials(obj):
            continue
        slots = [
            {
                "material": slot.material.name if slot.material else "",
                "link": slot.link,
            }
            for slot in obj.material_slots
        ]
        if not slots:
            continue
        layout[obj.name] = slots
    return layout


def get_material_overrides(
    current_layout: Dict[str, list],
    baseline_layout: Optional[Dict[str, list]] = None,
    container_name: Optional[str] = None,
) -> Dict[str, Dict[int, dict]]:
    """Return the material slots that were changed locally.

    Arguments:
        current_layout (Dict[str, list]): Layout of the objects as they are
            in the current scene, see :func:`get_material_layout`.
        baseline_layout (Optional[Dict[str, list]]): Layout recorded when the
            container was (last) loaded. When not available, e.g. for
            containers loaded before this feature existed, the slots are
            assumed to be local overrides when they don't reference a material
            that was loaded with the container.
        container_name (Optional[str]): Name of the container, used as the
            fallback for when no `baseline_layout` is available. Materials
            loaded with the container are prefixed with this name.

    Returns:
        Dict[str, Dict[int, dict]]: Object name mapped to the overridden slot
            indexes and their slot data.
    """
    baseline_layout = baseline_layout or {}
    overrides: Dict[str, Dict[int, dict]] = {}

    for obj_name, slots in current_layout.items():
        baseline = baseline_layout.get(obj_name)
        if baseline is None:
            changed = _get_legacy_overrides(slots, container_name)
        elif len(baseline) != len(slots):
            # Slots were added or removed locally. The slots no longer line up
            # with the baseline, so keep the layout as the artist left it.
            changed = dict(enumerate(slots))
        else:
            changed = {
                index: slot
                for index, (slot, base) in enumerate(zip(slots, baseline))
                if _normalize_slot(slot) != _normalize_slot(base)
            }

        if changed:
            overrides[obj_name] = changed

    return overrides


def apply_material_overrides(
    overrides: Dict[str, Dict[int, dict]],
    logger: Optional[logging.Logger] = None,
) -> List[str]:
    """Apply material slot overrides to the objects in the current file.

    Missing materials are skipped with a warning, so that an override on a
    material that is not published in the new version does not fail the whole
    update.

    Arguments:
        overrides (Dict[str, Dict[int, dict]]): Overrides to apply, as
            returned by :func:`get_material_overrides`.
        logger (Optional[logging.Logger]): Logger to report problems with.

    Returns:
        List[str]: Names of the objects that could not be found.
    """
    if not overrides:
        return []

    logger = logger or log
    missing_objects: List[str] = []

    for obj_name, slots in overrides.items():
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            logger.warning(
                "Unable to restore material overrides: object '%s' no "
                "longer exists in the loaded version.",
                obj_name,
            )
            missing_objects.append(obj_name)
            continue

        if not _supports_materials(obj):
            continue

        for index, slot_data in slots.items():
            index = int(index)
            material_name = slot_data.get("material") or ""
            material = None
            if material_name:
                material = bpy.data.materials.get(material_name)
                if material is None:
                    logger.warning(
                        "Unable to restore material '%s' on '%s': the "
                        "material does not exist in the loaded version.",
                        material_name,
                        obj_name,
                    )
                    continue

            # Make sure the slot exists on the newly loaded object, e.g. when
            # the artist had added extra slots to the object.
            while len(obj.material_slots) <= index:
                obj.data.materials.append(None)

            slot = obj.material_slots[index]
            link = slot_data.get("link") or "DATA"
            if slot.link != link:
                # Set the link type before the material to write the material
                # to the object instead of to the mesh data.
                slot.link = link
            if slot.material != material:
                slot.material = material

    return missing_objects


def get_preserved_material_names(
    overrides: Dict[str, Dict[int, dict]],
    container_name: Optional[str] = None,
) -> set:
    """Return the names of the materials referenced by the overrides.

    Loaders that delete the materials of the container on update use this to
    avoid deleting the materials the artist assigned locally. Materials that
    were loaded with the container are excluded, because those are re-created
    by the import itself; keeping them would only result in the new ones being
    suffixed with e.g. `.001`.

    Arguments:
        overrides (Dict[str, Dict[int, dict]]): Overrides, as returned by
            :func:`get_material_overrides`.
        container_name (Optional[str]): Name of the container whose materials
            are re-created on load and thus don't need preserving.

    Returns:
        set: Names of the materials used by the overrides.
    """
    prefix = f"{container_name}:" if container_name else None
    return {
        slot_data["material"]
        for slots in overrides.values()
        for slot_data in slots.values()
        if slot_data.get("material")
        and not (prefix and slot_data["material"].startswith(prefix))
    }


def _supports_materials(obj: Any) -> bool:
    """Return whether the object has material slots to manage."""
    data = getattr(obj, "data", None)
    return data is not None and hasattr(data, "materials")


def _normalize_slot(slot: dict) -> dict:
    """Normalize slot data read back from the container metadata.

    Blender's ID properties may return a nested group or a plain dict
    depending on how the data was written and on the Blender version, so
    the values are cast to their plain Python types for comparison.
    """
    if hasattr(slot, "to_dict"):
        slot = slot.to_dict()
    return {
        "material": str(slot.get("material") or ""),
        "link": str(slot.get("link") or "DATA"),
    }


def _get_legacy_overrides(
    slots: list,
    container_name: Optional[str],
) -> Dict[int, dict]:
    """Get overrides for containers that have no recorded baseline.

    Materials that were loaded together with the container are prefixed with
    the container name, e.g. `my_model_01_model:wood`. Slots referring to
    anything else were assigned locally by the artist.
    """
    if not container_name:
        return {}

    prefix = f"{container_name}:"
    return {
        index: slot
        for index, slot in enumerate(slots)
        if slot["material"] and not slot["material"].startswith(prefix)
    }
