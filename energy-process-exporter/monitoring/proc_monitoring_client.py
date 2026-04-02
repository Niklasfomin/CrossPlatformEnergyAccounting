import os
import ctypes
import struct

PERF_TYPE_HARDWARE = 0
PERF_COUNT_HW_INSTRUCTIONS = 1
PERF_COUNT_HW_CPU_CYCLES = 0
PERF_COUNT_HW_BRANCH_INSTRUCTIONS = 5
PERF_COUNT_HW_CACHE_MISSES = 9

class perf_event_attr(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint),
        ("size", ctypes.c_uint),
        ("config", ctypes.c_ulonglong),
        ("sample_period", ctypes.c_ulonglong),
        ("sample_type", ctypes.c_ulonglong),
        ("read_format", ctypes.c_ulonglong),
        ("flags", ctypes.c_ulonglong * 3),
    ]

def perf_event_open(attr, pid, cpu, group_fd, flags):
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    return libc.syscall(298, ctypes.byref(attr), pid, cpu, group_fd, flags)

def read_counter(fd):
    return struct.unpack("Q", os.read(fd, 8))[0]


def get_pmu_metrics(pid):
    attr = perf_event_attr()
    attr.type = PERF_TYPE_HARDWARE
    attr.size = ctypes.sizeof(perf_event_attr)

    results = {}

    # Instructions
    attr.config = PERF_COUNT_HW_INSTRUCTIONS
    fd_instr = perf_event_open(attr, pid, -1, -1, 0)
    results["instructions"] = read_counter(fd_instr) if fd_instr != -1 else None

    # Cycles
    attr.config = PERF_COUNT_HW_CPU_CYCLES
    fd_cycles = perf_event_open(attr, pid, -1, -1, 0)
    results["cycles"] = read_counter(fd_cycles) if fd_cycles != -1 else None

    # Branch instructions
    attr.config = PERF_COUNT_HW_BRANCH_INSTRUCTIONS
    fd_branch = perf_event_open(attr, pid, -1, -1, 0)
    results["branch_instructions"] = read_counter(fd_branch) if fd_branch != -1 else None

    # Cache misses
    attr.config = PERF_COUNT_HW_CACHE_MISSES
    fd_cache = perf_event_open(attr, pid, -1, -1, 0)
    results["cache_misses"] = read_counter(fd_cache) if fd_cache != -1 else None

    # Close valid fds
    for fd in [fd_instr, fd_cycles, fd_branch, fd_cache]:
        if fd != -1:
            os.close(fd)

    return results

def get_memory_usage(pid):
    try:
        with open(f"/proc/{pid}/statm") as f:
            parts = f.read().split()
            rss_pages = int(parts[1])
            page_size = os.sysconf("SC_PAGE_SIZE")
            rss_bytes = rss_pages * page_size
            return rss_bytes
    except Exception:
        return None

def get_cpu_usage(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().split()
            utime = int(parts[13])
            stime = int(parts[14])
            return utime + stime
    except Exception:
        return None

def get_all_metrics(pid):
    metrics = {}
    pmu = get_pmu_metrics(pid)
    if pmu:
        metrics.update(pmu)
    mem = get_memory_usage(pid)
    if mem is not None:
        metrics["memory_rss_bytes"] = mem
    cpu = get_cpu_usage(pid)
    if cpu is not None:
        metrics["cpu_time_ticks"] = cpu
    return metrics