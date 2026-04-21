import threading

import docker


class DockerManager:
    def __init__(self):
        self.client = docker.from_env()
        self.docker_container_to_pids_to_metrics = {}

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

    def merge_containers_with_pids_and_metrics(self, pid_callback=None):
        if pid_callback:
            print("Merging container events with PID updates...")
        return
