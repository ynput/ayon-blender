import bpy

from ayon_core.pipeline import CreatedInstance, AutoCreator
from ayon_blender.api.plugin import BlenderCreator
from ayon_blender.api.constants import (
    AYON_PROPERTY,
    AYON_INSTANCES,
    AYON_CONTAINERS
)


class CreateWorkfile(BlenderCreator, AutoCreator):
    """Workfile auto-creator.

    The workfile instance stores its data on the `AYON_WORKFILE` collection
    as custom attributes, because unlike other instances it doesn't have an
    instance node of its own.

    """
    identifier = "io.ayon.creators.blender.workfile"
    label = "Workfile"
    product_type = "workfile"
    icon = "fa5.file"

    def create(self):
        """Create workfile instances."""
        workfile_instance = next(
            (
                instance for instance in self.create_context.instances
                if instance.creator_identifier == self.identifier
            ),
            None,
        )

        project_entity = self.create_context.get_current_project_entity()
        project_name = project_entity["name"]
        folder_entity = self.create_context.get_current_folder_entity()
        folder_path = folder_entity["path"]
        task_entity = self.create_context.get_current_task_entity()
        task_name = task_entity["name"]
        host_name = self.create_context.host_name

        if not workfile_instance:
            product_name = self.get_product_name(
                project_name,
                folder_entity,
                task_entity,
                task_name,
                host_name,
            )
            data = {
                "folderPath": folder_path,
                "task": task_name,
                "variant": task_name,
            }
            data.update(
                self.get_dynamic_data(
                    project_name,
                    folder_entity,
                    task_entity,
                    task_name,
                    host_name,
                    workfile_instance,
                )
            )
            self.log.info("Auto-creating workfile instance...")
            workfile_instance = CreatedInstance(
                self.product_type, product_name, data, self
            )
            self._add_instance_to_context(workfile_instance)

        elif (
            workfile_instance["folderPath"]  != folder_path
            or workfile_instance["task"] != task_name
        ):
            # Update instance context if it's different
            product_name = self.get_product_name(
                project_name,
                folder_entity,
                task_entity,
                self.default_variant,
                host_name,
            )

            workfile_instance["folderPath"] = folder_path
            workfile_instance["task"] = task_name
            workfile_instance["productName"] = product_name

    def collect_instances(self):
        instance_node = bpy.data.collections.get(AYON_INSTANCES)
        if not instance_node:
            return

        property = instance_node.get(AYON_PROPERTY)
        if not property:
            return

        # Create instance object from existing data
        instance = CreatedInstance.from_existing(
            instance_data=property.to_dict(),
            creator=self
        )
        instance.transient_data["instance_node"] = instance_node

        # Add instance to create context
        self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        """Override abstract method from BlenderCreator.
        Store changes of existing instances so they can be recollected.

        Args:
            update_list(List[UpdateData]): Changed instances
                and their changes, as a list of tuples.
        """

        for created_instance, _ in update_list:
            data = created_instance.data_to_store()
            node = created_instance.transient_data.get("instance_node")
            if not node:
                node = self._create_ayon_instances_collection()
            else:
                node = self._transfer_workfile_property(node)

            self.imprint(node, data)

            created_instance.transient_data["instance_node"] = node

    def _transfer_workfile_property(
            self, node: bpy.types.Collection)-> bpy.types.Collection:
        """Transfer all workfile-related instance data from
        AYON_CONTAINERS to AYON_INSTANCES if any. Backward
        compatibility only.

        Args:
            node (bpy.types.Collection): instance node

        Returns:
            bpy.types.Collection: instance node
        """
        if (
            not isinstance(node, bpy.types.Collection)
            or node.name != AYON_CONTAINERS
            or AYON_PROPERTY not in node
        ):
            return node

        instance_node = bpy.data.collections.get(AYON_INSTANCES)
        if not instance_node:
            instance_node = self._create_ayon_instances_collection()
        instance_node[AYON_PROPERTY] = node.get(AYON_PROPERTY)
        del node[AYON_PROPERTY]
        return instance_node

    def remove_instances(self, instances):
        for instance in instances:
            node = instance.transient_data.get("instance_node")
            if node:
                if node.children or node.objects:
                    # If it has members, keep collection around
                    # but only remove imprinted data
                    del node[AYON_PROPERTY]
                else:
                    # Delete the collection
                    bpy.data.collections.remove(node)

            self._remove_instance_from_context(instance)
