import os
import pprint
import re
import threading
import time

from cgroupspy import trees


class CgroupV2:
    def __init__(self, pid_map_callback=None):
        self.pids = set()
        self.path_to_pids = {}
        self.lock = threading.Lock()
        self.container_names_to_pids = {}
        self.pid_count_per_container = {}
        self.pid_map_callback = pid_map_callback

    # def run(self, monitor_active):
    #     while monitor_active:
    #         # Continously search for new processes spawning in containers
    #         threading.Thread(target=self.monitor_pid_updates).start()
    #         time.sleep(1)  # Adjust the sleep time as needed

    def handle_container_event(self, container_id, event_type, container_name):
        if event_type == "start":
            print(f"Container event: {event_type} for ({container_name})")
            # Find the cgroup path for this container
            target_pids = set(self.container_names_to_pids.get(container_name, []))
            cgroup_path = None
            for path, pids in self.path_to_pids.items():
                if set(pids) == target_pids and target_pids:
                    cgroup_path = path
                    break
            if cgroup_path:
                threading.Thread(
                    target=self.monitor_new_pids_for_container,
                    args=(container_name, cgroup_path),
                    daemon=True,
                ).start()

            # Match cgroup and init mapping from containers to PIDs
            self.path_to_pids = self.find_docker_cgroups_with_pids()
            self.match_containers_with_pids(
                container_id, container_name, self.path_to_pids
            )
            # Find the cgroup path for this container
            target_pids = set(self.container_names_to_pids.get(container_name, []))
            cgroup_path = None
            for path, pids in self.path_to_pids.items():
                if set(pids) == target_pids and target_pids:
                    cgroup_path = path
                    break
            if cgroup_path:
                threading.Thread(
                    target=self.monitor_new_pids_for_container,
                    args=(container_name, cgroup_path),
                    daemon=True,
                ).start()
            else:
                print(f"Could not find cgroup path for {container_name}")
        elif event_type == "die":
            print(f"Container event: {event_type} for ({container_name} with ID)")
            print(f"Removing stopped container {container_name} with from mapping")
            try:
                del self.container_names_to_pids[container_name]
            except KeyError:
                print(f"Container {container_name} not found in mapping during removal")

    def find_docker_cgroups_with_pids(self):
        cgroup_paths = self._find_cgroup_paths()
        return self._get_pids_for_cgroup_paths(cgroup_paths)

    def _find_cgroup_paths(self):
        t = trees.Tree()
        pattern = re.compile(r"docker-[0-9a-f]{64}\.scope")
        cgroup_paths = []
        for node in t.root.walk():
            if pattern.search(node.name.decode()):
                try:
                    full_path_str = node.full_path.decode()
                    cgroup_paths.append(full_path_str)
                except Exception as e:
                    print(
                        f"Found inactive container without cgroup path...ignoring. Error: {e}"
                    )
        return cgroup_paths

    def _get_pids_for_cgroup_paths(self, cgroup_paths):
        for full_path_str in cgroup_paths:
            try:
                with open(full_path_str + "/cgroup.procs") as f:
                    pids = [int(x) for x in f.read().split()]
                    self.pids.update(pids)
                    with self.lock:
                        if full_path_str not in self.path_to_pids:
                            self.path_to_pids[full_path_str] = pids
            except Exception as e:
                print(f"Error reading PIDs for {full_path_str}: {e}")
        return self.path_to_pids

    def match_containers_with_pids(self, container_id, container_name, path_to_pids):
        for path, pids in self.path_to_pids.items():
            if container_id in path:
                self.container_names_to_pids[container_name] = pids
                print(f"Container | Initial PIDs: {self.container_names_to_pids}")
                if self.pid_map_callback:
                    self.pid_map_callback(self.container_names_to_pids)
                return self.container_names_to_pids

    def monitor_new_pids_for_container(
        self, container_name, cgroup_path, poll_interval=1
    ):
        """Monitor the cgroup.procs file for new PIDs and report them."""
        procs_file = os.path.join(cgroup_path, "cgroup.procs")
        seen_pids = set()
        while True:
            try:
                with open(procs_file) as f:
                    current_pids = set(int(x) for x in f.read().split())
                new_pids = current_pids - seen_pids
                if new_pids:
                    with self.lock:
                        self.container_names_to_pids[container_name] = list(
                            current_pids
                        )
                        if self.pid_map_callback:
                            self.pid_map_callback(self.container_names_to_pids)
                        pprint.pprint(self.container_names_to_pids)
                        print("Current container to PIDs map:")
                    for pid in new_pids:
                        print(f"[{container_name}] New PID detected: {pid}")
                seen_pids = current_pids
            except Exception:
                pass
            time.sleep(poll_interval)
