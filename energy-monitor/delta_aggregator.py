import os
import pprint
import re

from accumulation.cgroups import CgroupV2
from accumulation.docker import DockerManager
from database.DBClient import DBClient
from exporter.exporter import PrometheusExporter
from monitoring.monitor_client import MonitoringClient
from smart_meter_api_wrapper.smart_meter import SmartMeterAPIClient

HZ = os.sysconf("SC_CLK_TCK")
import argparse
import threading
import time
from collections import deque
from math import isfinite

from cgroupspy import trees

INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "my-super-secret-auth-token"
INFLUX_ORG = "myorg"
INFLUX_BUCKET = "mybucket"


class DeltaAggregator:
    def __init__(
        self,
        interval=1.0,
        sample_rate=0.1,
        db_client=None,
        exporter=None,
        docker_manager=None,
        cgroups_manager=None,
        meter_client=None,
        meter_sensor_id="L1",
    ):
        self.monitor = MonitoringClient()
        self.interval = interval
        self.exporter = exporter
        self.docker_manager = docker_manager
        self.cgroups_manager = cgroups_manager
        self.sample_rate = sample_rate
        self.db_client = db_client
        self.meter_client = meter_client
        self.meter_sensor_ids = [s.strip() for s in meter_sensor_id.split(",")]
        self.snapshots = deque(maxlen=2)  # Store only last two process metric snapshots
        self.running = False
        self.thread = threading.Thread(target=self._collect, daemon=True)

    def start(self):
        self.running = True
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join()

    def _collect(self):
        while self.running:
            interval_start = time.time()
            avg_power = 0.0
            interval_energy = 0.0
            while (time.time() - interval_start) < self.interval:
                sample_time = time.time()
                sleep_time = self.sample_rate - (time.time() - sample_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            interval_end = time.time()
            if self.meter_client:
                power_samples = []
                try:
                    power = sum(
                        self.meter_client.get_power_usage(sid)
                        for sid in self.meter_sensor_ids
                    )
                    if power is not None:
                        power_samples.append(power)
                except Exception as e:
                    print(f"Error fetching power data: {e}")
                avg_power = (
                    sum(power_samples) / len(power_samples) if power_samples else 0.0
                )
                actual_interval = interval_end - interval_start
                interval_energy = avg_power * actual_interval

            process_data = self.monitor.get_process_list()
            self.snapshots.append((interval_end, process_data))

            if len(self.snapshots) == 2:
                interval, deltas = self.get_delta()
                # Send deltas to DockerManager if present
                if deltas and self.docker_manager is not None:
                    self.docker_manager.merge_containers_with_pids_from_deltas(deltas)
                # Push deltas to aggregation layer
                if deltas and self.db_client and self.meter_client is None:
                    print(f"[{time.strftime('%X')}] delta count: {len(deltas)}")
                    self.db_client.write_deltas(
                        timestamp=interval_end,
                        interval=interval,
                        deltas=deltas,
                    )
                elif self.db_client and self.meter_client:
                    print(
                        f"[{time.strftime('%X')}] delta count: {len(deltas)}, avg_power: {avg_power}, interval_energy: {interval_energy}"
                    )
                    self.db_client.write_deltas(
                        timestamp=interval_end,
                        interval=interval,
                        deltas=deltas,
                        interval_energy=interval_energy,
                        avg_power=avg_power,
                    )
                elif self.db_client is None and self.meter_client is None:
                    if self.exporter is not None:
                        self.exporter.set_process_metrics(
                            timestamp=interval_end,
                            interval=interval,
                            deltas=deltas,
                            node="localhost",
                        )

    def get_delta(self):
        if len(self.snapshots) < 2:
            return None, {}

        (t1, d1), (t2, d2) = self.snapshots[0], self.snapshots[-1]
        dict1 = {proc["pid"]: proc for proc in d1}
        dict2 = {proc["pid"]: proc for proc in d2}
        interval = t2 - t1
        deltas = {}

        for pid in set(dict1) & set(dict2):
            prev = dict1[pid]
            curr = dict2[pid]

            delta_cpu_ns = self._delta(curr, prev, "cpu_time_ns", clamp_monotonic=True)
            delta_io_bytes = self._delta(
                curr, prev, "disk_io_bytes", clamp_monotonic=True
            )
            delta_net_send_bytes = self._delta(
                curr, prev, "net_send_bytes", clamp_monotonic=True
            )
            delta_syscalls = self._delta(
                curr, prev, "syscall_count", clamp_monotonic=True
            )
            delta_ctx_switches = self._delta(
                curr, prev, "context_switches", clamp_monotonic=True
            )
            delta_cpu_time_psutil = self._delta(
                curr, prev, "psutil_cpu_time_ns", clamp_monotonic=True
            )
            delta_cpu_time_ticks = self._delta(
                curr, prev, "cpu_time_ticks", clamp_monotonic=True
            )
            delta_instruction = self._delta(
                curr, prev, "instructions", clamp_monotonic=True
            )
            delta_branch_instr = self._delta(
                curr, prev, "branch_instructions", clamp_monotonic=True
            )
            delta_cycles = self._delta(curr, prev, "cycles", clamp_monotonic=True)
            delta_cache_misses = self._delta(
                curr, prev, "cache_misses", clamp_monotonic=True
            )
            delta_rss_memory = self._delta(
                curr, prev, "memory_rss_bytes", clamp_monotonic=False
            )
            # ticks in ns
            delta_cpu_time_proc_ns = delta_cpu_time_ticks * (1e9 / HZ)

            ppid = curr.get("ppid")
            if ppid is None:
                ppid = -1

            deltas[pid] = {
                "pid": pid,
                "ppid": int(ppid),
                "name": curr.get("name") or "",
                "delta_cpu_ns": int(delta_cpu_ns),
                "delta_io_bytes": int(delta_io_bytes),
                "delta_net_send_bytes": int(delta_net_send_bytes),
                "context_switches": int(delta_ctx_switches),
                "syscall_count": int(delta_syscalls),
                "delta_rss_memory": int(delta_rss_memory),
                "delta_cpu_time_psutil": int(delta_cpu_time_psutil),
                "delta_cpu_time_proc": int(delta_cpu_time_proc_ns),
                "instructions": int(delta_instruction),
                "cycles": int(delta_cycles),
                "branch_instructions": int(delta_branch_instr),
                "cache_misses": int(delta_cache_misses),
            }

            prev_classes = prev.get("syscall_classes") or {}
            curr_classes = curr.get("syscall_classes") or {}
            all_classes = set(prev_classes) | set(curr_classes)
            deltas[pid]["syscall_class_deltas"] = {
                cls: int(
                    self._num(curr_classes.get(cls)) - self._num(prev_classes.get(cls))
                )
                for cls in all_classes
            }

        return interval, deltas

    def _num(self, v):
        """Coerce any value to a finite float; None/NaN/invalid -> 0."""
        if v is None:
            return 0.0
        try:
            x = float(v)
            return x if isfinite(x) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _delta(self, curr, prev, key, clamp_monotonic=True):
        """
        Safe delta for (mostly) monotonic counters.
        If clamp_monotonic is True, negative deltas (reset/rollover) are clamped to 0.
        """
        d = self._num(curr.get(key)) - self._num(prev.get(key))
        if clamp_monotonic and d < 0:
            d = 0.0
        return d


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run Process Monitoring with optional Prometheus Exporter, InfluxDB and Smart Meter integration"
    )
    parser.add_argument(
        "--use-prometheus-exporter",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable Prometheus Exporter (disabled by default)",
    )
    parser.add_argument(
        "--exporter-addr",
        default=os.getenv("EXPORTER_ADDR"),
        help="Prometheus Expoter host (default: env EXPORTER_ADDR)",
    )
    parser.add_argument(
        "--exporter-port",
        default=os.getenv("EXPORTER_PORT"),
        help="Prometheus Expoter port (default: env EXPORTER_PORT)",
    )
    parser.add_argument(
        "--use-influxdb",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable InfluxDB integration (disabled by default)",
    )
    parser.add_argument(
        "--influx-url",
        # default=INFLUX_URL,
        help="InfluxDB URL (default: http://localhost:8086)",
    )
    parser.add_argument(
        "--influx-token",
        # default=INFLUX_TOKEN,
        help="InfluxDB token (default: my-super-secret-auth-token)",
    )
    parser.add_argument(
        "--influx-org",
        # default=INFLUX_ORG,
        help="InfluxDB org (default: myorg)",
    )
    parser.add_argument(
        "--influx-bucket",
        # default=INFLUX_BUCKET,
        help="InfluxDB bucket (default: mybucket)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Aggregation window in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=None,
        help="Sampling rate in seconds (optional; defaults to interval)",
    )
    parser.add_argument(
        "--use-meter",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable smart meter integration (disabled by default)",
    )
    parser.add_argument(
        "--meter-host",
        default=os.getenv("SMARTMETER_HOST"),
        help="Smart meter host (default: env SMARTMETER_HOST)",
    )
    parser.add_argument(
        "--meter-user",
        default=os.getenv("SMARTMETER_USER"),
        help="Smart meter username (default: env SMARTMETER_USER)",
    )
    parser.add_argument(
        "--meter-password",
        default=os.getenv("SMARTMETER_PASSWORD"),
        help="Smart meter password (default: env SMARTMETER_PASSWORD)",
    )
    parser.add_argument(
        "--meter-ssl",
        action="store_true",
        help="Enable SSL for smart meter client (optional)",
    )
    parser.add_argument(
        "--meter-sensor-id",
        default="L1",
        help="Sensor id to read from smart meter (default: L1)",
    )

    args = parser.parse_args()

    sample_rate = args.sample_rate if args.sample_rate is not None else args.interval

    print(
        f"Starting Interval Metric Aggregation: interval={args.interval}, sample_rate={sample_rate}"
    )
    db_client = None
    if args.use_influxdb:
        print(
            f"Influx: {args.influx_url} (org={args.influx_org}, bucket={args.influx_bucket})"
        )
        db_client = DBClient(
            args.influx_url, args.influx_token, args.influx_org, args.influx_bucket
        )

    meter_client = None
    meter_sensor_id = "L1"
    if args.use_meter:
        if not args.meter_host:
            raise ValueError("--meter-host is required when --use-meter is enabled")
        meter_sensor_id = args.meter_sensor_id
        meter_client = SmartMeterAPIClient(
            host=args.meter_host,
            ssl=args.meter_ssl,
            username=args.meter_user,
            password=args.meter_password,
        )
    else:
        print("Smart meter integration disabled")

    exporter = None
    if args.use_prometheus_exporter:
        if not args.exporter_addr or not args.exporter_port:
            raise ValueError(
                "--exporter-addr and --exporter-port is required when --use-prometheus-exporter is enabled"
            )
        exporter = PrometheusExporter(node="localhost", addr="127.0.0.1", port=8000)

    cgroups_manager = CgroupV2()
    docker_manager = DockerManager(cgroups_manager)
    # CgroupV2(pid_map_callback=docker_manager.get_latest_container_to_pid_mapping)

    monitor = DeltaAggregator(
        interval=args.interval,
        sample_rate=sample_rate,
        db_client=db_client,
        meter_client=meter_client,
        meter_sensor_id=meter_sensor_id,
        exporter=exporter,
        cgroups_manager=cgroups_manager,
        docker_manager=docker_manager,
    )

    # Pass the callback to DockerManager so cgroups_manager receives container events
    docker_manager.run(callback=cgroups_manager.handle_container_event)

    monitor.start()
    # cgroups_manager.run(monitor.running)
    print("Monitoring started. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        monitor.stop()
        if db_client:
            db_client.close()
        print("Monitoring stopped.")
