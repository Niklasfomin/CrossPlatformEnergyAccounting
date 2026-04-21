import prometheus_client as prom
from typing_extensions import Dict

PROCESS_METRICS = [
    ("delta_cpu_ns", "CPU time delta in nanoseconds"),
    ("delta_io_bytes", "I/O bytes delta"),
    ("delta_net_send_bytes", "Network send bytes delta"),
    ("context_switches", "Context switches count"),
    ("syscall_count", "Syscall count"),
    ("delta_rss_memory", "RSS memory delta"),
    ("delta_cpu_time_psutil", "CPU time delta (psutil)"),
    ("delta_cpu_time_proc", "CPU time delta (proc)"),
    ("delta_instructions", "Instructions delta"),
    ("delta_cycles", "CPU cycles delta"),
    ("delta_branch_instructions", "Branch instructions delta"),
    ("delta_cache_misses", "Cache misses delta"),
]

METRIC_NAMES = [
    "delta_cpu_ns",
    "delta_io_bytes",
    "delta_net_send_bytes",
    "context_switches",
    "syscall_count",
    "delta_rss_memory",
    "delta_cpu_time_psutil",
    "delta_cpu_time_proc",
    "delta_instructions",
    "delta_cycles",
    "delta_branch_instructions",
    "delta_cache_misses",
]

METRIC_LABELS = ["node", "pid", "process_name", "ppid", "interval", "timestamp"]


class PrometheusExporter:
    def __init__(self, node, addr, port):
        self.node = node
        self.addr = addr
        self.port = port
        self.process_metrics = {
            name: prom.Gauge(name, desc, METRIC_LABELS)
            for name, desc in PROCESS_METRICS
        }
        prom.start_http_server(port, addr)

    def set_metrics(self, timestamp, interval, deltas, node="localhost") -> Dict:
        for pid, d in deltas.items():
            self.process_metrics["delta_cpu_ns"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("delta_cpu_ns", 0)))
            self.process_metrics["delta_io_bytes"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("delta_io_bytes", 0)))
            self.process_metrics["delta_net_send_bytes"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("delta_net_send_bytes", 0)))
            self.process_metrics["context_switches"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("context_switches", 0)))
            self.process_metrics["syscall_count"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("syscall_count", 0)))
            self.process_metrics["delta_rss_memory"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("delta_rss_memory", 0)))
            self.process_metrics["delta_cpu_time_psutil"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(float(d.get("delta_cpu_time_psutil", 0)))
            self.process_metrics["delta_cpu_time_proc"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(float(d.get("delta_cpu_time_proc", 0)))
            self.process_metrics["delta_instructions"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("instructions", 0)))
            self.process_metrics["delta_cycles"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("cycles", 0)))
            self.process_metrics["delta_branch_instructions"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("branch_instructions", 0)))
            self.process_metrics["delta_cache_misses"].labels(
                node=node,
                pid=pid,
                process_name=d.get("name", ""),
                ppid=d.get("ppid", ""),
                interval=interval,
                timestamp=timestamp,
            ).set(int(d.get("cache_misses", 0)))
            # for cls, cnt in d.get("syscall_class_deltas", {}).items():
            #     self.process_metrics[f"syscall_class_{cls}"].labels(
            #         node=node,
            #         pid=pid,
            #         process_name=d.get("name", ""),
            #         ppid=d.get("ppid", ""),
            #         interval=interval,
            #     ).set(int(cnt))
        return self.process_metrics
