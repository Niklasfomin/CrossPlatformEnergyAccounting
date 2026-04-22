import pprint
import threading

import docker

from accumulation.cgroups import CgroupV2


class DockerManager:
    def __init__(self, cgroups: CgroupV2):
        self.client = docker.from_env()
        self.docker_container_to_pids_to_metrics = {}
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

    def merge_containers_with_pids_and_metrics(self, deltas):
        print("DEBUG: merge_containers_with_pids_and_metrics called")
        print(f"DEBUG: deltas argument: {deltas}")
        container_to_pids = self.cgroups.get_container_names_to_pids()
        print(f"DEBUG: container_to_pids from cgroups: {container_to_pids}")
        if container_to_pids is None:
            print("DEBUG: container_to_pids is None!")
        elif len(container_to_pids) == 0:
            print("DEBUG: container_to_pids is empty!")
        else:
            pprint.pprint(container_to_pids)
            print(
                f"Merging container events with PID and metrics updates... ({len(container_to_pids)} containers)"
            )
            # Merge the latest container to PID mapping with the deltas
            for container_name, pids in container_to_pids.items():
                print(
                    f"DEBUG: Aggregating metrics for container: {container_name}, pids: {pids}"
                )
                for pid in pids:
                    print(f"DEBUG: Checking if pid {pid} is in deltas...")
                    if pid in deltas:
                        print(
                            f"Container: {container_name}, PID: {pid}, Metrics: {deltas[pid]}"
                        )
                    else:
                        print(f"DEBUG: PID {pid} not found in deltas.")
