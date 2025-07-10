import bpy

from ayon_core.pipeline import CreatedInstance, AutoCreator
from ayon_blender.api.plugin import BlenderCreator
from ayon_blender.api.pipeline import convert_avalon_containers
from ayon_blender.api.constants import (
    AYON_PROPERTY,
    AYON_CONTAINERS
)


class CreateWorkfile(BlenderCreator, AutoCreator):
    """Workfile auto-creator.

    The workfile instance stores its data on the `AYON_CONTAINERS` collection
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

        convert_avalon_containers()
        instance_node = bpy.data.collections.get(AYON_CONTAINERS)
        if not instance_node:
            instance_node = bpy.data.collections.new(name=AYON_CONTAINERS)
        workfile_instance.transient_data["instance_node"] = instance_node

    def collect_instances(self):

        instance_node = bpy.data.collections.get(AYON_CONTAINERS)
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

    def remove_instances(self, instances):
        for instance in instances:
            node = instance.transient_data["instance_node"]
            del node[AYON_PROPERTY]

            self._remove_instance_from_context(instance)
