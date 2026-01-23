import ayon_api
import pyblish.api

from ayon_blender.api import plugin

from ayon_core.pipeline.farm.pyblish_functions import (
    create_skeleton_instance,
    create_instances_for_aov
)

class CollectLocalRenderInstances(plugin.BlenderInstancePlugin):
    """Collect instances for local render.
    """
    order = pyblish.api.CollectorOrder + 0.31
    families = ["render"]

    label = "Collect local render instances"

    transfer_keys = {
        "creator_attributes",
        "publish_attributes",
    }

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Render on farm is enabled. "
                           "Skipping local render collecting.")
            return

        self.log.debug("Expected files for local render: %s",
                       instance.data.get("expectedFiles"))

        self._precollect_required_data(instance)

        # Use same logic as how instances get created for farm submissions
        skeleton = create_skeleton_instance(
            instance,
            # TODO: These should be fixed in core to just allow the default
            #  None to work
            families_transfer=[],
            instance_transfer={},
        )
        for key in self.transfer_keys:
            if key in instance.data:
                skeleton[key] = instance.data[key]

        aov_instances = create_instances_for_aov(
            instance=instance,
            skeleton=skeleton,
            aov_filter={"blender": [".*"]},  # allow all as reviewables
            skip_integration_repre_list=[],
            do_not_add_review=False,
        )

        # Create instances for each AOV
        context = instance.context
        anatomy = context.data["anatomy"]

        render_target: str = instance.data.get("creator_attributes", {}).get(
            "render_target", "local"
        )

        # Add the instances directly to the current publish context
        for aov_instance_data in aov_instances:
            # Make a shallow copy of transient data because it'll likely
            # contain data that can't be deep-copied, e.g. Blender objects.
            if "transientData" in instance.data:
                aov_instance_data["transientData"] = dict(
                    instance.data["transientData"]
                )

            # The `create_instances_for_aov` makes some paths rootless paths,
            # like the "stagingDir" for each representation which we will make
            # absolute again.
            for repre in aov_instance_data["representations"]:
                repre["stagingDir"] = anatomy.fill_root(repre["stagingDir"])

            aov_instance = context.create_instance(
                aov_instance_data["productName"]
            )
            aov_instance.data.update(aov_instance_data)

            families = [f"render.{render_target}"]
            if "review" in aov_instance.data["families"]:
                families.append("review")
            aov_instance.data["families"] = families

        # Skip integrating original render instance.
        # We are not removing it because it's used to trigger the render.
        instance.data["integrate"] = False

    def _precollect_required_data(self, instance):
        """Ensure required data is present.
        
        Some data may not exist yet in the instance at this point, so we need
        to ensure it is there for certain function calls, like
        `create_instances_for_aov` requiring `taskEntity` in instance data
        if setting `use_legacy_product_names_for_renders` is disabled which is
        usually collected at a later order by `CollectAnatomyInstanceData`.
        """""

        project_name: str = instance.context.data["projectName"]

        # Add folderEntity
        if "folderEntity" not in instance.data:
            self.log.debug("Collecting folder entity for instance...")
            instance.data["folderEntity"] = ayon_api.get_folder_by_path(
                project_name=project_name,
                folder_path=instance.data["folderPath"],
            )
        folder_entity = instance.data["folderEntity"]

        # Add taskEntity
        if "taskEntity" not in instance.data:
            self.log.debug("Collecting task entity for instance...")
            project_name: str = instance.context.data["projectName"]
            instance.data["taskEntity"] = ayon_api.get_task_by_name(
                project_name=project_name,
                task_name=instance.data["task"],
                folder_id=folder_entity["id"],
            )
