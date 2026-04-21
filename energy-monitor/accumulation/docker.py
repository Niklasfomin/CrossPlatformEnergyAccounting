import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Set

import docker

from accumulation.aggregate_metrics import MetricsAggregatorInterface


class DockerManager:
    def __init__(self):
        self.client = docker.from_env()
        # Registry for per-container aggregators: container_name -> DockerMetricsAggregator
        self.container_aggregators: Dict[str, DockerMetricsAggregator] = {}

    # def handle_container_start(self, container_id, container_name):
    #     # Create a new aggregator for this container (keyed by container_name)
    #     aggregator = DockerMetricsAggregator(
    #         container_id=container_id, container_name=container_name
    #     )
    #     self.container_aggregators[container_name] = aggregator

    # def handle_container_die(self, container_id, container_name):
    #     # Remove aggregator when container dies (keyed by container_name)
    #     if container_name in self.container_aggregators:
    #         del self.container_aggregators[container_name]

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
        """
        Watches for container start events from the Docker event stream.
        Logs the full event and container name. Removes 'scope' from the top level and 'Attributes' from 'Actor'.
        Calls callback with (container_id, "start", container_name) if provided.
        Also creates a DockerMetricsAggregator for each started container.
        """
        events = self.client.events(decode=True, filters={"event": "start"})
        start_events = []
        for event in events:
            if event.get("Type") == "container" and event.get("Action") == "start":
                event = dict(event)  # Make a copy to avoid mutating the original event
                event.pop("scope", None)
                event.pop("time", None)
                event.pop("timeNano", None)
                # Remove Attributes from Actor if present
                container_id = None
                container_name = None
                if "Actor" in event:
                    if "Attributes" in event["Actor"]:
                        container_name = event["Actor"]["Attributes"].get("name")
                        event["Actor"] = dict(event["Actor"])  # Copy Actor dict
                        event["Actor"].pop("Attributes", None)
                    container_id = event["Actor"].get("ID")
                # Create aggregator for this container
                # if container_id and container_name:
                #     self.handle_container_start(container_id, container_name)
                if callback and container_id:
                    callback(container_id, "start", container_name)
                start_events.append(event)
        return start_events

    def get_container_die_events(self, callback=None):
        """
        Returns a list of container die events (when a container is killed or finished) from the Docker event stream.
        Logs the entire event for debugging.
        Trims 'scope' from the top level and 'Attributes' from the nested 'Actor' dict.
        Calls callback with (container_id, "die", container_name) if provided.
        Also removes the DockerMetricsAggregator for each stopped container.
        """
        events = self.client.events(decode=True, filters={"event": "die"})
        die_events = []
        for event in events:
            if event.get("Type") == "container" and event.get("Action") == "die":
                event = dict(event)  # Make a copy to avoid mutating the original event
                event.pop("scope", None)
                event.pop("time", None)
                event.pop("timeNano", None)
                # Remove Attributes from Actor if present
                container_id = None
                container_name = None
                if "Actor" in event:
                    if "Attributes" in event["Actor"]:
                        container_name = event["Actor"]["Attributes"].get("name")
                        event["Actor"] = dict(event["Actor"])  # Copy Actor dict
                        event["Actor"].pop("Attributes", None)
                    container_id = event["Actor"].get("ID")
                # Remove aggregator for this container
                # if container_name:
                #     self.handle_container_die(container_id, container_name)
                if callback and container_id:
                    callback(container_id, "die", container_name)
                die_events.append(event)
        return die_events


@dataclass
class DockerProcessMetrics:
    container_id: str
    container_name: str
    pids: Set[int] = field(default_factory=set)
    pid_metrics: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    container_metrics: Dict[str, Any] = field(default_factory=dict)

    def add_pid(self, pid: int):
        self.pids.add(pid)

    def set_pid_metrics(self, pid: int, metrics: Dict[str, Any]):
        self.pid_metrics[pid] = metrics

    def aggregate_metrics(self) -> Dict[str, Any]:
        # Example: sum all metrics for all pids
        aggregated = {}
        for metrics in self.pid_metrics.values():
            for k, v in metrics.items():
                aggregated[k] = aggregated.get(k, 0) + v
        return aggregated


class DockerMetricsAggregator(MetricsAggregatorInterface):
    def __init__(self, container_id: str, container_name: str):
        self.metrics = DockerProcessMetrics(
            container_id=container_id, container_name=container_name
        )

    def set_pid_metrics(self, pid: int, metrics: Dict[str, Any]):
        self.metrics.add_pid(pid)
        self.metrics.set_pid_metrics(pid, metrics)

    def aggregate_metrics(self) -> Dict[str, Any]:
        return self.metrics.aggregate_metrics()

    def log_container_metrics(self):
        """
        Logs the aggregated metrics for this container in a readable format.
        """
        metrics = self.aggregate_metrics()
        print(f"Container: {self.metrics.container_name}")
        for metric, value in metrics.items():
            print(f"  {metric}: {value}")
        print("-" * 40)
