from monitoring.monitor_client import MonitoringClient
from smart_meter_api_wrapper.smart_meter import SmartMeterAPIClient
import time
import os
import threading
import copy
import psutil

class BPFMonitorThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.monitor_client = MonitoringClient()
        self.running = True

    def run(self):
        while self.running:
            time.sleep(0.1)

    def stop(self):
        self.running = False


def calucate_sum_of_cpu_time(process_data):
    return sum(proc["cpu_time_ns"] for proc in process_data)

def calucate_sum_of_cpu_time_psutil(process_data):
    return sum(proc["psutil_cpu_time_ns"] for proc in process_data)

def get_total_cpu_time_psutil():
    total = 0.0
    for proc in psutil.process_iter(['cpu_times']):
        try:
            times = proc.info['cpu_times']
            total += times.user + times.system
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def aggregate_data_and_estimate():
    num_cores = os.cpu_count()
    print("Number of CPU cores:", num_cores)
    bpf_thread = BPFMonitorThread()
    bpf_thread.start()
    smart_meter_client = SmartMeterAPIClient(host=os.getenv("SMARTMETER_HOST"),
                                             ssl=False,
                                             username=os.getenv("SMARTMETER_USER"),
                                             password=os.getenv("SMARTMETER_PASSWORD"))

    prev_process_data = {}
    min_interval = 2  # seconds
    last_cpu_power = 0.0
    start = get_total_cpu_time_psutil()
    time_delta = time.perf_counter()
    try:
        while True:
            time.sleep(min_interval)
            power_usage = smart_meter_client.get_power_usage(node="siena17")
            print("Power usage in watts: ", power_usage)
            process_data = bpf_thread.monitor_client.get_process_list()
            stop = get_total_cpu_time_psutil()
            delta_total_cpu_time_psutil = stop - start
            start = stop
            real_interval = time.perf_counter() - time_delta
            time_delta = time.perf_counter()

            print("Number of monitored processes: ", len(process_data))
            measured_cpu_time = bpf_thread.monitor_client.bpf_client.get_total_cpu_time()
            cpu_time_ns = calucate_sum_of_cpu_time(process_data)
            cpu_time_ns_psutil = calucate_sum_of_cpu_time_psutil(process_data)
            cpu_time_ns_psutil_prev = calucate_sum_of_cpu_time_psutil(process_data)
            delta_cpu_time_psutil = cpu_time_ns_psutil - cpu_time_ns_psutil_prev
            total_bpf = process_data[0]["total"] if process_data else 0
            delta_total_cpu_time= total_bpf - last_cpu_power
            last_cpu_power = total_bpf

            # Delta calculation
            for proc in process_data:
                pid = proc["pid"]
                prev = prev_process_data.get(pid, {})
                delta_cpu_time = proc["cpu_time_ns"] - prev.get("cpu_time_ns", 0)
                delta_syscalls = proc["syscall_count"] - prev.get("syscall_count", 0)
                delta_ctx_switches = proc["context_switches"] - prev.get("context_switches", 0)
                delta_disk_io = proc["disk_io_bytes"] - prev.get("disk_io_bytes", 0)
                delta_net_send = proc["net_send_bytes"] - prev.get("net_send_bytes", 0)
                delta_total = proc["total"] - prev.get("total", 0)
                delta_psutil_cpu_time = proc["psutil_cpu_time_ns"] - prev.get("psutil_cpu_time_ns", 0)

                psutil_power = power_usage * (delta_psutil_cpu_time / delta_cpu_time_psutil) if delta_cpu_time_psutil > 0 else 0
                process_power = power_usage * (delta_cpu_time / delta_total_cpu_time) if delta_total_cpu_time > 0 else 0

                print(f"PID: {pid}, Name: {proc['name']}, ΔCPU Time (bpf): {delta_cpu_time}, "
                      f"ΔCPU Time (bpf): {delta_psutil_cpu_time},"
                      f"Power Usage (W): {process_power}, Total: {delta_total}")

            # Update previous data
            prev_process_data = {proc["pid"]: copy.deepcopy(proc) for proc in process_data}

            print("Total CPU time (bpf pure) : ", total_bpf)
            print("Total CPU time (sum/bpf) in ns: ", cpu_time_ns)
            print("Total CPU time (sum/bpf) in s: ", cpu_time_ns / 1e9)

            print("Total CPU time (psutil sum) in ns: ", cpu_time_ns_psutil)
            print("Measured total CPU time (psutil) in ns: ", measured_cpu_time)
            print("Measured total CPU time (psutil) in s: ", measured_cpu_time / 1e9)

            print("Measure interval: ", real_interval, "s")
            print("Delta total CPU time: ", delta_total_cpu_time)
            print("Delta total CPU time in s: ", delta_total_cpu_time / 1e9)
            print(f"Delta CPU time (psutil, interval window): {delta_total_cpu_time_psutil:.2f} s")
            print(f"Delta CPU time (psutil, sum): {psutil_power:.2f} s")
    finally:
        bpf_thread.stop()
        bpf_thread.join()


aggregate_data_and_estimate()