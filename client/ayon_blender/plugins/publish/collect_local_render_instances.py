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

            families = ["render.local"]
            if "review" in aov_instance.data["families"]:
                families.append("review")
            aov_instance.data["families"] = families

        # Skip integrating original render instance.
        # We are not removing it because it's used to trigger the render.
        instance.data["integrate"] = False
