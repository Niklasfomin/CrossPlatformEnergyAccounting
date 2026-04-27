import pprint
import threading

import docker
import pandas as pd

from accumulation.cgroups import CgroupV2


class DockerManager:
    def __init__(self, cgroups: CgroupV2):
        self.client = docker.from_env()
        self.docker_container_to_pids_to_metrics = {}
        self.docker_container_to_pids_to_metrics_summed = {}
        self.cgroups = cgroups

    def run(self, callback=None):
        start_thread = threading.Thread(
            target=self.get_container_start_events, args=(callback,), daemon=True
        )
        die_thread = threading.Thread(
            target=self.get_container_die_events, args=(callback,), daemon=True
        )
        start_thread.start()
        die_thread.start()

    def get_container_start_events(self, callback=None):
        events = self.client.events(decode=True, filters={"event": "start"})
        start_events = []
        for event in events:
            if event.get("Type") == "container" and event.get("Action") == "start":
                container_id = None
                container_name = None
                if "Actor" in event:
                    if "Attributes" in event["Actor"]:
                        container_name = event["Actor"]["Attributes"].get("name")
                    container_id = event["Actor"].get("ID")
                if callback and container_id:
                    callback(container_id, "start", container_name)
                start_events.append(event)
        return start_events

    def get_container_die_events(self, callback=None):
        events = self.client.events(decode=True, filters={"event": "die"})
        die_events = []
        for event in events:
            if event.get("Type") == "container" and event.get("Action") == "die":
                container_id = None
                container_name = None
                if "Actor" in event:
                    if "Attributes" in event["Actor"]:
                        container_name = event["Actor"]["Attributes"].get("name")
                    container_id = event["Actor"].get("ID")
                if callback and container_id:
                    callback(container_id, "die", container_name)
                die_events.append(event)
        return die_events

    def get_latest_container_to_pid_mapping(self, pid_callback=None):
        if pid_callback:
            print("Merging container events with PID and metrics updates...")
        return self.cgroups.get_container_names_to_pids()

    def merge_containers_with_pids_from_deltas(self, deltas):
        container_to_pids = self.cgroups.get_container_names_to_pids()
        print(f"DEBUG: container_to_pids from cgroups: {container_to_pids}")
        if container_to_pids is None:
            print("DEBUG: container_to_pids is None!")
        elif len(container_to_pids) == 0:
            print("DEBUG: container_to_pids is empty!")
        else:
            pprint.pprint(container_to_pids)
            # Merge the latest container to PID mapping with the deltas
            for container_name, pids in container_to_pids.items():
                print(f"DEBUG: Aggregating metrics for container: {container_name}")
                # Check if at least some PIDs are in deltas
                missing_pids = [pid for pid in pids if pid not in deltas]
                matching_pids = [pid for pid in pids if pid in deltas]
                # Func call to merge metrics for matching PIDs and aggregate per container
                self.get_container_deltas_summed(
                    container_to_pids, matching_pids, deltas
                )
                self.get_container_pids_deltas(container_to_pids, matching_pids, deltas)
                print(
                    f"Container: {container_name}, Matching PIDs in deltas: {matching_pids}"
                )

                print(
                    f"Container: {container_name}, Missing PIDs in deltas: {len(missing_pids)}"
                )
                # if matching_pids:
                #     print(
                #         f"Container: {container_name}, Matching PIDs in deltas: {matching_pids}"
                #     )
                # else:
                #     print(
                #         f"DEBUG: No PIDs for container {container_name} found in deltas."
                #     )

    def get_container_pids_deltas(self, container_to_pids, matching_pids, deltas):
        for container in container_to_pids:
            if container not in self.docker_container_to_pids_to_metrics:
                self.docker_container_to_pids_to_metrics[container] = {}
            for pid in matching_pids:
                self.docker_container_to_pids_to_metrics[container][pid] = deltas[pid]
        return self.docker_container_to_pids_to_metrics

    def get_container_deltas_summed(self, container_to_pids, matching_pids, deltas):
        # Sum metrics for all matching_pids
        metrics_list = [deltas[pid] for pid in matching_pids if pid in deltas]
        if metrics_list:
            df = pd.DataFrame(metrics_list)
            summed_metrics = df.sum(numeric_only=True).to_dict()
        else:
            summed_metrics = {}
        for container in container_to_pids:
            self.docker_container_to_pids_to_metrics_summed[container] = summed_metrics
        return self.docker_container_to_pids_to_metrics_summed
