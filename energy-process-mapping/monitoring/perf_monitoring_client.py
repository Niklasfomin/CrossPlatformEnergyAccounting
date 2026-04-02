import os
import ctypes
import ctypes.util
import struct
import time
from threading import Event

try:
    from monitoring.bpf_monitoring_client import BPFMonitoringClient
except ImportError:
    BPFMonitoringClient = None

PERF_TYPE_HARDWARE = 0
PERF_TYPE_SOFTWARE = 1

PERF_EVENTS = [
    ("cycles", PERF_TYPE_HARDWARE, 0),
    ("instructions", PERF_TYPE_HARDWARE, 1),
    ("cache_references", PERF_TYPE_HARDWARE, 2),
    ("cache_misses", PERF_TYPE_HARDWARE, 3),
    ("branch_instructions", PERF_TYPE_HARDWARE, 4),
    ("branch_misses", PERF_TYPE_HARDWARE, 5),
    ("task_clock", PERF_TYPE_SOFTWARE, 1),
]

class perf_event_attr(ctypes.Structure):
    _fields_ = [
        ('type', ctypes.c_uint),
        ('size', ctypes.c_uint),
        ('config', ctypes.c_ulong),
        ('sample_period', ctypes.c_ulong),
        ('sample_type', ctypes.c_ulong),
        ('read_format', ctypes.c_ulong),
        ('flags', ctypes.c_ulong),
        ('wakeup_events', ctypes.c_uint),
        ('bp_type', ctypes.c_uint),
        ('bp_addr', ctypes.c_ulong),
        ('bp_len', ctypes.c_ulong),
    ]

libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)

def perf_event_open(attr, pid, cpu, group_fd, flags):
    __NR_perf_event_open = 298 if os.uname().machine == 'x86_64' else 336
    return libc.syscall(__NR_perf_event_open, ctypes.byref(attr), pid, cpu, group_fd, flags)

def open_perf_counter(pid=-1, cpu=-1, config=0, event_type=PERF_TYPE_HARDWARE):
    attr = perf_event_attr()
    attr.type = event_type
    attr.size = ctypes.sizeof(perf_event_attr)
    attr.config = config
    attr.disabled = 1
    attr.exclude_kernel = 0
    attr.exclude_hv = 0
    fd = perf_event_open(attr, pid, cpu, -1, 0)
    if fd < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return fd

def read_perf_counter(fd):
    data = os.read(fd, 8)
    return struct.unpack('Q', data)[0]

def enable_counter(fd):
    libc.ioctl(fd, 0x2400)  # PERF_EVENT_IOC_ENABLE

def disable_counter(fd):
    libc.ioctl(fd, 0x2401)  # PERF_EVENT_IOC_DISABLE

def reset_counter(fd):
    libc.ioctl(fd, 0x2402)  # PERF_EVENT_IOC_RESET

def open_perf_counter_cgroup(cgroup_fd, cpu=-1, config=0, event_type=PERF_TYPE_HARDWARE):
    attr = perf_event_attr()
    attr.type = event_type
    attr.size = ctypes.sizeof(perf_event_attr)
    attr.config = config
    attr.disabled = 1
    attr.exclude_kernel = 0
    attr.exclude_hv = 0
    PERF_FLAG_PID_CGROUP = 1 << 3
    fd = perf_event_open(attr, -1, cpu, cgroup_fd, PERF_FLAG_PID_CGROUP)
    if fd < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return fd

def open_cgroup_fd(cgroup_path):
    return os.open(cgroup_path, os.O_RDONLY)

def get_cpu_count():
    try:
        return os.cpu_count()
    except Exception:
        with open("/proc/cpuinfo") as f:
            return sum(1 for line in f if line.startswith("processor"))

class PerfTickCollector:
    def __init__(
        self,
        pid_list=None,
        cgroup_paths=None,
        enable_cpu_mode=True,
        enable_bpf_monitoring=False,
        interval=1.0,
        data_callback=None,
    ):
        self.pid_list = pid_list if pid_list is not None else [os.getpid()]
        self.cgroup_paths = cgroup_paths if cgroup_paths is not None else []
        self.enable_cpu_mode = enable_cpu_mode
        self.enable_bpf_monitoring = (
            enable_bpf_monitoring and BPFMonitoringClient is not None
        )
        self.interval = interval
        self.data_callback = data_callback

        self.pid_fds = {}
        self.cgroup_fds = {}
        self.cpu_fds = {}
        self.prev_pid_vals = {}
        self.prev_cgroup_vals = {}
        self.prev_cpu_vals = {}

        self.stop_event = Event()

        # --- BPF Monitoring Client ---
        self.bpf_monitor = BPFMonitoringClient() if self.enable_bpf_monitoring else None

        self._setup_counters()

    def _setup_counters(self):
        # Per-PID
        for pid in self.pid_list:
            self.pid_fds[pid] = {}
            for event_name, event_type, config in PERF_EVENTS:
                fd = open_perf_counter(pid=pid, config=config, event_type=event_type)
                self.pid_fds[pid][event_name] = fd

        # Per-cgroup
        for path in self.cgroup_paths:
            cg_fd = open_cgroup_fd(path)
            self.cgroup_fds[path] = {}
            for event_name, event_type, config in PERF_EVENTS:
                perf_fd = open_perf_counter_cgroup(
                    cg_fd, config=config, event_type=event_type
                )
                self.cgroup_fds[path][event_name] = (cg_fd, perf_fd)

        # Per-CPU
        if self.enable_cpu_mode:
            cpu_count = get_cpu_count()
            for cpu in range(cpu_count):
                self.cpu_fds[cpu] = {}
                for event_name, event_type, config in PERF_EVENTS:
                    fd = open_perf_counter(
                        pid=-1, cpu=cpu, config=config, event_type=event_type
                    )
                    self.cpu_fds[cpu][event_name] = fd

        # Enable all
        for fd_dict in self.pid_fds.values():
            for fd in fd_dict.values():
                reset_counter(fd)
                enable_counter(fd)
        for event_dict in self.cgroup_fds.values():
            for cg_fd, perf_fd in event_dict.values():
                reset_counter(perf_fd)
                enable_counter(perf_fd)
        for fd_dict in self.cpu_fds.values():
            for fd in fd_dict.values():
                reset_counter(fd)
                enable_counter(fd)

    def _collect_pid(self):
        result = {}
        for pid, fd_dict in self.pid_fds.items():
            result[pid] = {}
            for event_name, fd in fd_dict.items():
                value = read_perf_counter(fd)
                key = (pid, event_name)
                prev_value = self.prev_pid_vals.get(key, value)
                delta = value - prev_value
                if event_name == "task_clock":
                    cpu_usage = (delta / (self.interval * 1e9)) * 100
                    result[pid][event_name] = {
                        "delta_ns": delta,
                        "cpu_percent": cpu_usage,
                    }
                else:
                    result[pid][event_name] = delta
                self.prev_pid_vals[key] = value
        return result

    def _collect_cgroup(self):
        result = {}
        for path, event_dict in self.cgroup_fds.items():
            result[path] = {}
            for event_name, (cg_fd, perf_fd) in event_dict.items():
                value = read_perf_counter(perf_fd)
                key = (path, event_name)
                prev_value = self.prev_cgroup_vals.get(key, value)
                delta = value - prev_value
                if event_name == "task_clock":
                    cpu_usage = (delta / (self.interval * 1e9)) * 100
                    result[path][event_name] = {
                        "delta_ns": delta,
                        "cpu_percent": cpu_usage,
                    }
                else:
                    result[path][event_name] = delta
                self.prev_cgroup_vals[key] = value
        return result

    def _collect_cpu(self):
        result = {}
        for cpu, fd_dict in self.cpu_fds.items():
            result[cpu] = {}
            for event_name, fd in fd_dict.items():
                value = read_perf_counter(fd)
                key = (cpu, event_name)
                prev_value = self.prev_cpu_vals.get(key, value)
                delta = value - prev_value
                if event_name == "task_clock":
                    cpu_usage = (delta / (self.interval * 1e9)) * 100
                    result[cpu][event_name] = {
                        "delta_ns": delta,
                        "cpu_percent": cpu_usage,
                    }
                else:
                    result[cpu][event_name] = delta
                self.prev_cpu_vals[key] = value
        return result

    def run(self):
        print(
            "Ticked perf counter polling for PIDs/cgroups/CPUs/metrics, printing per-tick delta values. Ctrl+C to exit..."
        )
        try:
            while not self.stop_event.is_set():
                timestamp = time.time()
                deltas = {"timestamp": timestamp}
                deltas["pids"] = self._collect_pid()
                deltas["cgroups"] = self._collect_cgroup()
                if self.enable_cpu_mode:
                    deltas["cpus"] = self._collect_cpu()
                # --- INTEGRATE BPF data ---
                if self.enable_bpf_monitoring and self.bpf_monitor is not None:
                    try:
                        bpf_data = self.bpf_monitor.get_process_list()
                    except Exception as e:
                        bpf_data = {"error": str(e)}
                    deltas["bpf"] = bpf_data
                # Use callback if provided
                if self.data_callback is not None:
                    self.data_callback(deltas)
                else:
                    print("Per-tick deltas:", deltas)
                time.sleep(self.interval)
        except KeyboardInterrupt:
            self.stop_event.set()
        finally:
            self.cleanup()
            print("Stopped.")

    def cleanup(self):
        for fd_dict in self.pid_fds.values():
            for fd in fd_dict.values():
                disable_counter(fd)
                os.close(fd)
        for event_dict in self.cgroup_fds.values():
            for cg_fd, perf_fd in event_dict.values():
                disable_counter(perf_fd)
                os.close(perf_fd)
                os.close(cg_fd)
        for fd_dict in self.cpu_fds.values():
            for fd in fd_dict.values():
                disable_counter(fd)
                os.close(fd)

def get_all_pids():
    """Return a list of all currently running process IDs (PIDs)."""
    pids = []
    for entry in os.listdir('/proc'):
        if entry.isdigit():
            pids.append(int(entry))
    return pids


if __name__ == "__main__":
    def my_data_callback(data):
        print("Per-tick deltas:", data)

    collector = PerfTickCollector(
        pid_list=[],
        cgroup_paths=[],
        enable_cpu_mode=True,
        enable_bpf_monitoring=False,  # <---- ENABLE BPF HERE
        interval=1.0,
        data_callback=my_data_callback,
    )
    collector.run()