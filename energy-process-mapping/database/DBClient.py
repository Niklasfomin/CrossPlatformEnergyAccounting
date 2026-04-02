from influxdb_client import InfluxDBClient, Point, WritePrecision
import pandas as pd

class DBClient:
    def __init__(self, url, token, org, bucket):
        self.client = InfluxDBClient(url=url, token=token, org=org,timeout=360_000)
        self.write_api = self.client.write_api()
        self.bucket = bucket

    def write_deltas(self, timestamp, interval, deltas, avg_power, interval_energy, node="localhost"):
        for pid, d in deltas.items():
            point = (
                Point("process_interval_metrics")
                .tag("node", node)
                .tag("pid", str(pid))
                .tag("process_name", d.get("name", ""))
                .field("interval", float(interval))
                .field("delta_cpu_ns", int(d.get('delta_cpu_ns', 0)))
                .field("delta_io_bytes", int(d.get('delta_io_bytes', 0)))
                .field("delta_net_send_bytes", int(d.get('delta_net_send_bytes', 0)))
                .field("context_switches", int(d.get('context_switches', 0)))
                .field("syscall_count", int(d.get('syscall_count', 0)))
                .field("delta_rss_memory", int(d.get('delta_rss_memory', 0)))
                .field("delta_cpu_time_psutil", float(d.get('delta_cpu_time_psutil', 0)))
                .field("delta_cpu_time_proc", float(d.get('delta_cpu_time_proc', 0)))
                .field("avg_power", float(avg_power))
                .field("interval_energy", float(interval_energy))
                .field("delta_instructions", int(d.get('instructions', 0)))
                .field("delta_cycles", int(d.get('cycles', 0)))
                .field("delta_branch_instructions", int(d.get('branch_instructions', 0)))
                .field("delta_cache_misses", int(d.get('cache_misses', 0)))
                .time(int(timestamp * 1e9), WritePrecision.NS)
            )
            for cls, cnt in d.get('syscall_class_deltas', {}).items():
                point = point.field(f"syscall_class_{cls}", int(cnt))

            self.write_api.write(bucket=self.bucket, record=point)

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
            self.write_api = None

    def load_data(self):
        query = '''
            from(bucket: "mybucket")
              |> range(start: -1h)
              |> filter(fn: (r) =>
                r._measurement == "process_interval_metrics" and
                (
                  r._field == "delta_cpu_ns" or
                  r._field == "delta_io_bytes" or
                  r._field == "delta_net_send_bytes" or
                  r._field == "context_switches" or
                  r._field == "syscall_count" or
                  r._field == "delta_rss_memory" or
                  r._field == "delta_cpu_time_psutil" or
                  r._field == "delta_cpu_time_proc" or
                  r._field == "syscall_class_file" or
                  r._field == "syscall_class_network" or
                  r._field == "syscall_class_memory" or
                  r._field == "syscall_class_process" or
                  r._field == "syscall_class_other" or
                  r._field == "syscall_class_sched" or
                  r._field == "syscall_class_signal" or
                  r._field == "syscall_class_time" or 
                  r._field == "interval_energy" or
                  r._field == "avg_power"
                )
              )
              |> map(fn: (r) => ({ r with _value: float(v: r._value) }))
              |> aggregateWindow(every: 1s, fn: mean, createEmpty: false)
              |> group(columns: ["pid", "process_name"])
              |> pivot(
                  rowKey: ["_time", "pid", "process_name"],
                  columnKey: ["_field"],
                  valueColumn: "_value"
              )
              |> keep(columns: [
                  "_time", "pid", "process_name",
                  "delta_cpu_ns", "delta_io_bytes", "delta_net_send_bytes", "context_switches",
                  "syscall_count", "delta_rss_memory", "delta_cpu_time_psutil", "delta_cpu_time_proc", "avg_power",
                  "syscall_class_file", "syscall_class_network", "syscall_class_memory", "syscall_class_process",
                  "syscall_class_other", "syscall_class_sched", "syscall_class_signal", "syscall_class_time", "interval_energy"
              ])
              |> sort(columns: ["_time", "pid"])
        '''
        dfs = self.client.query_api().query_data_frame(query, org="myorg")
        df = pd.concat(dfs) if isinstance(dfs, list) else dfs
        df = df.drop(columns=[c for c in ['result', 'table'] if c in df.columns])
        df['_time'] = pd.to_datetime(df['_time'])
        df = df.sort_values(['_time', 'pid'])
        return df


