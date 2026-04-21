import pprint
import re
import threading
import time

from cgroupspy import trees


class CgroupV2:
    def __init__(self):
        self.pids = set()
        self.path_to_pids = {}
        self.lock = threading.Lock()
        self.container_names_to_pids = {}

    def run(self, monitor_active):
        while monitor_active:
            self.find_docker_cgroups()

    def handle_container_event(self, container_id, event_type, container_name):
        if event_type == "start":
            print(f"Container event: {event_type} for ({container_name})")
            # Match cgroup and update mapping
            self.path_to_pids = self.find_docker_cgroups()
            self.match_containers_with_pids(
                container_id, container_name, self.path_to_pids
            )
        elif event_type == "die":
            print(f"Container event: {event_type} for ({container_name} with ID)")
            print(f"Removing stopped container {container_name} with from mapping")
            try:
                del self.container_names_to_pids[container_name]
            except KeyError:
                print(f"Container {container_name} not found in mapping during removal")

    def find_docker_cgroups(self):
        t = trees.Tree()
        pattern = re.compile(r"docker-[0-9a-f]{64}\.scope")
        for node in t.root.walk():
            if pattern.search(node.name.decode()):
                try:
                    full_path_str = node.full_path.decode()  # decode bytes to str
                    with open(full_path_str + "/cgroup.procs") as f:
                        pids = [int(x) for x in f.read().split()]
                        self.pids.update(pids)
                        # Thread-safe addition to prevent duplicates
                        with self.lock:
                            if full_path_str not in self.path_to_pids:
                                self.path_to_pids[full_path_str] = pids
                except Exception as e:
                    print(
                        f"Found inactive container without cgroup path...ignoring. Error: {e}"
                    )
        return self.path_to_pids

    def match_containers_with_pids(self, container_id, container_name, path_to_pids):
        for path, pids in self.path_to_pids.items():
            if container_id in path:
                self.container_names_to_pids[container_name] = pids
                print(f"Container | PIDs: {self.container_names_to_pids}")
                return self.container_names_to_pids
