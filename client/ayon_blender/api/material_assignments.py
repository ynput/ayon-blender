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

A material counts as published when the recorded baseline assigns it to a
slot. Anything else was assigned locally, including datablocks Blender
duplicated on the artist's behalf, e.g. `my_model_01_model:wood.001`. Those
copies therefore need to be excluded from the datablocks a loader removes
before the new version is imported, see :func:`get_preserved_material_names`
and :func:`get_members_still_in_use`.

Containers loaded before this feature existed have no baseline. For those the
slots are compared by name prefix instead, which cannot tell a duplicated
published material apart from a published one. They get a baseline recorded on
their next update and are handled exactly from then on.

An empty slot is represented by an empty string, because Blender's ID
properties cannot store `None` values.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

import bpy

log = logging.getLogger(__name__)

# Datablock types that a locally duplicated material can reference and that a
# loader may remove together with the container. Objects and meshes are
# deliberately excluded: they are always removed with the container, and
# Blender reports the scene as a user of every object, which would otherwise
# keep the whole container around.
_DEPENDENCY_TYPES = tuple(
    datablock_type
    for datablock_type in (
        getattr(bpy.types, name, None)
        for name in ("Material", "Image", "NodeTree", "Texture")
    )
    if datablock_type is not None
)


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
            `OBJECT`). Material-capable objects without slots are included as
            empty lists.
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
        layout[obj.name] = slots
    return layout


def get_material_overrides(
    current_layout: Dict[str, list],
    baseline_layout: Optional[Dict[str, list]] = None,
    container_name: Optional[str] = None,
) -> Dict[str, dict]:
    """Return the material slot changes that were made locally.

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
        Dict[str, dict]: Object name mapped to a dict with the `slots` that
            differ from the baseline (slot index mapped to its slot data) and
            the `slot_count` to restore, which is `None` when the artist did
            not change the amount of slots.
    """
    baseline_layout = baseline_layout or {}
    overrides: Dict[str, dict] = {}

    for obj_name in set(current_layout) | set(baseline_layout):
        current = current_layout.get(obj_name)
        baseline = baseline_layout.get(obj_name)

        if baseline is None:
            # No baseline for this object. Fall back to telling locally
            # assigned materials apart by their name.
            slots = _get_legacy_overrides(current or [], container_name)
            if slots:
                overrides[obj_name] = {"slots": slots, "slot_count": None}
            continue

        if current is None:
            # Every material slot was removed locally.
            overrides[obj_name] = {"slots": {}, "slot_count": 0}
            continue

        # Compare slot by slot so that slots the artist did not touch keep
        # following the published file, even when the amount of slots differs.
        # Slots beyond the baseline are slots the artist added.
        slots = {
            index: slot
            for index, slot in enumerate(current)
            if (
                index >= len(baseline)
                or _normalize_slot(slot) != _normalize_slot(baseline[index])
            )
        }

        slot_count = None
        if len(current) < len(baseline):
            # Slots were removed locally, so restore that amount as well.
            slot_count = len(current)

        if slots or slot_count is not None:
            overrides[obj_name] = {"slots": slots, "slot_count": slot_count}

    return overrides


def apply_material_overrides(
    overrides: Dict[str, dict],
    logger: Optional[logging.Logger] = None,
) -> List[str]:
    """Apply material slot overrides to the objects in the current file.

    Missing materials are skipped with a warning, so that an override on a
    material that is not published in the new version does not fail the whole
    update.

    Arguments:
        overrides (Dict[str, dict]): Overrides to apply, as returned by
            :func:`get_material_overrides`.
        logger (Optional[logging.Logger]): Logger to report problems with.

    Returns:
        List[str]: Names of the objects that could not be found.
    """
    if not overrides:
        return []

    logger = logger or log
    missing_objects: List[str] = []

    for obj_name, override in overrides.items():
        slots = override.get("slots") or {}
        slot_count = override.get("slot_count")

        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            # Only warn when there was an assignment to restore. A pure slot
            # count override for an object that no longer exists is expected
            # and harmless.
            if slots:
                logger.warning(
                    "Unable to restore material overrides: object '%s' no "
                    "longer exists in the loaded version.",
                    obj_name,
                )
                missing_objects.append(obj_name)
            continue

        if not _supports_materials(obj):
            continue

        if slot_count is not None:
            _remove_material_slots_after(obj, slot_count)

        # Apply in slot order so that slots which have to be appended are
        # created in the right order.
        for index in sorted(slots, key=int):
            _apply_slot_override(
                obj, int(index), slots[index], obj_name, logger
            )

    return missing_objects


def get_preserved_material_names(
    overrides: Dict[str, dict],
    baseline_layout: Optional[Dict[str, list]] = None,
) -> set:
    """Return the names of the materials that must survive the update.

    Loaders that remove the materials of the container before importing the
    new version use this to avoid deleting materials the artist assigned or
    duplicated locally. Materials the published file assigns to a slot are
    excluded, because those are re-created by the import itself; keeping them
    would only result in the new ones being suffixed with e.g. `.001`.

    Arguments:
        overrides (Dict[str, dict]): Overrides, as returned by
            :func:`get_material_overrides`.
        baseline_layout (Optional[Dict[str, list]]): Layout of the container
            as it was loaded. Materials assigned by it are considered
            published. When not available, all override materials are kept.

    Returns:
        set: Names of the materials to preserve.
    """
    published = {
        _normalize_slot(slot)["material"]
        for slots in (baseline_layout or {}).values()
        for slot in slots
    }
    published.discard("")

    return {
        slot_data["material"]
        for override in overrides.values()
        for slot_data in (override.get("slots") or {}).values()
        if slot_data.get("material")
        and slot_data["material"] not in published
    }


def get_members_still_in_use(members: set) -> set:
    """Return the container members that are still used outside the container.

    Loaders remove every datablock that was loaded with the container. A
    material the artist duplicated and edited locally is not part of the
    container though, so removing its dependencies such as images and node
    groups would leave that copy broken. Those dependencies are returned here
    so the caller can keep them.

    Arguments:
        members (set): Datablocks that are about to be removed.

    Returns:
        set: The members that have a user outside of `members`.
    """
    dependencies = {
        member for member in members
        if isinstance(member, _DEPENDENCY_TYPES)
    }
    if not dependencies:
        return set()

    user_map = bpy.data.user_map(subset=dependencies)
    preserved = set()
    while True:
        removable = members - preserved
        needed = {
            member for member, users in user_map.items()
            if set(users) - removable
        }
        if needed <= preserved:
            return preserved
        preserved.update(needed)


def _apply_slot_override(obj, index, slot_data, obj_name, logger):
    """Apply a single material slot override to `obj`."""
    material_name = slot_data.get("material") or ""
    material = None
    if material_name:
        material = bpy.data.materials.get(material_name)
        if material is None:
            logger.warning(
                "Unable to restore material '%s' on '%s': the material does "
                "not exist in the loaded version.",
                material_name,
                obj_name,
            )
            return

    # Make sure the slot exists on the newly loaded object, e.g. when the
    # artist had added extra slots to the object.
    while len(obj.material_slots) <= index:
        obj.data.materials.append(None)

    slot = obj.material_slots[index]
    link = slot_data.get("link") or "DATA"
    if slot.link != link:
        # Set the link type before the material to write the material to the
        # object instead of to the mesh data.
        slot.link = link
    if slot.material != material:
        slot.material = material


def _remove_material_slots_after(obj, count: int):
    """Remove the material slots of `obj` with an index of `count` and up."""
    materials = obj.data.materials
    if count <= 0:
        # Popping the last material leaves an empty slot behind in Blender,
        # clearing removes them all.
        materials.clear()
        return
    while len(materials) > count:
        materials.pop(index=len(materials) - 1)


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

    Note:
        A duplicated published material keeps the prefix, e.g.
        `my_model_01_model:wood.001`, and is indistinguishable from a
        published material here. Those containers get a baseline recorded on
        this update and are handled exactly from then on.
    """
    if not container_name:
        return {}

    prefix = f"{container_name}:"
    return {
        index: slot
        for index, slot in enumerate(slots)
        if slot["material"] and not slot["material"].startswith(prefix)
    }
