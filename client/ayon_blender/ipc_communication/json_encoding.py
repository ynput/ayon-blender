import json

from ayon_core.lib import IconBase, get_icon_def_from_data

from ayon_core.tools.common_models import (
    TagItem,
    ProductTypeIconMapping,
    ProjectItem,
    StatusItem,
    FolderItem,
    TaskItem,
    FolderTypeItem,
    TaskTypeItem,
)
from ayon_core.tools.loader.abstract import (
    ProductItem,
    ProductTypeItem,
    RepreItem,
    ActionItem,
    ProductTypesFilter,
)
from ayon_core.tools.common_models.users import UserItem

OBJ_TYPE_ID_KEY = "__obj_type__"


class DataEncoder(json.JSONEncoder):
    def default(self, obj):
        if obj is None:
            return None

        if isinstance(obj, (list, dict, str, int, float, bool)):
            return obj

        if isinstance(obj, set):
            return {
                OBJ_TYPE_ID_KEY: "py_set",
                "data": list(obj),
            }

        if isinstance(obj, IconBase):
            data = obj.to_data()
            data[OBJ_TYPE_ID_KEY] = "IconBase"
            return data

        type_name = type(obj).__name__
        if isinstance(
            obj, (
                ProjectItem,
                StatusItem,
                FolderTypeItem,
                TaskTypeItem,
                ProductTypeItem,
                FolderItem,
                TaskItem,
                ProductItem,
                RepreItem,
                ActionItem,
            )
        ):
            data = obj.to_data()
            data[OBJ_TYPE_ID_KEY] = type_name
            return data

        if isinstance(obj, UserItem):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "username": obj.username,
                "full_name": obj.full_name,
                "email": obj.email,
                "avatar_url": obj.avatar_url,
                "active": obj.active,
            }

        if isinstance(obj, ProductTypesFilter):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "product_types": obj.product_types,
                "is_allow_list": obj.is_allow_list,
            }

        if isinstance(obj, ProductTypeIconMapping):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "default": obj._default,
                "definitions": obj._definitions,
            }

        if isinstance(obj, TagItem):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "name": obj.name,
                "color": obj.color,
            }

        return super().default(obj)


class DataDecoder(json.JSONDecoder):
    def __init__(self, **kwargs):
        kwargs["object_hook"] = self.object_hook
        super().__init__(**kwargs)

    def object_hook(self, obj):
        name = obj.pop(OBJ_TYPE_ID_KEY, None)
        if name is None:
            return obj

        decoder = getattr(self, f"decode_{name}")
        return decoder(obj)

    def decode_py_set(self, obj):
        return set(obj["data"])

    def decode_IconBase(self, obj):
        return get_icon_def_from_data(obj)

    def decode_ProjectItem(self, obj):
        return ProjectItem.from_data(obj)

    def decode_StatusItem(self, obj):
        return StatusItem.from_data(obj)

    def decode_FolderTypeItem(self, obj):
        return FolderTypeItem.from_data(obj)

    def decode_TaskTypeItem(self, obj):
        return TaskTypeItem.from_data(obj)

    def decode_ProductTypeItem(self, obj):
        return ProductTypeItem.from_data(obj)

    def decode_FolderItem(self, obj):
        return FolderItem.from_data(obj)

    def decode_TaskItem(self, obj):
        return TaskItem.from_data(obj)

    def decode_ProductItem(self, obj):
        return ProductItem.from_data(obj)

    def decode_RepreItem(self, obj):
        return RepreItem.from_data(obj)

    def decode_ActionItem(self, obj):
        return ActionItem.from_data(obj)

    def decode_UserItem(self, obj):
        return UserItem(**obj)

    def decode_ProductTypesFilter(self, obj):
        return ProductTypesFilter(**obj)

    def decode_ProductTypeIconMapping(self, obj):
        return ProductTypeIconMapping(obj["default"], obj["definitions"])

    def decode_TagItem(self, obj):
        return TagItem(**obj)

