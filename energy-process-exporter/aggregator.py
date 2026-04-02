import time
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from monitoring.bpf_monitoring_client import BPFMonitoringClient
from smart_meter_api_wrapper.smart_meter import SmartMeterAPIClient
from monitoring.monitor_client import MonitoringClient
import os
from dotenv import load_dotenv
load_dotenv()

# InfluxDB config
INFLUX_URL = ""
INFLUX_TOKEN = ""
INFLUX_ORG = ""
INFLUX_BUCKET = ""

def get_process_metrics(client):
  """Returns process metrics"""
  return client.get_process_list()

def get_node_power(client):
  """Returns node power consumption in watts"""
  return client.get_power_usage(node="siena17")

def write_metrics(monitor_client, smart_meter_client):
  client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
  write_api = client.write_api(write_options=SYNCHRONOUS)

  while True:
    timestamp = datetime.now()

    # Collect and write node power metric
    power_watts = get_node_power(client=smart_meter_client)
    power_point = Point("node_metrics") \
      .tag("node", "siena17") \
      .field("power_watts", power_watts) \
      .time(timestamp, WritePrecision.NS)
    write_api.write(bucket=INFLUX_BUCKET, record=power_point)

    # Collect and write process metrics
    processes = get_process_metrics(monitor_client)
    for process in processes:
      # Create base point
      print(process)
      point = Point("process_metrics") \
        .tag("pid", str(process['pid'])) \
        .tag("process_name", process['name']) \
        .field("cpu_time_ns", process['cpu_time_ns']) \
        .field("cpu_usage_percent", process['cpu_usage_percent']) \
        .field("syscall_count", process['syscall_count']) \
        .field("context_switches", process['context_switches']) \
        .field("disk_io_bytes", process['disk_io_bytes']) \
        .field("net_send_bytes", process['net_send_bytes']) \
        .field("instructions", process['instructions']) \
        .field("cycles", process['cycles']) \
        .field("branch_instructions", process['branch_instructions']) \
        .time(timestamp, WritePrecision.NS)

      if 'cpu_time_ticks' in process and process['cpu_time_ticks'] is not None:
        point = point.field("cpu_time_ticks", process['cpu_time_ticks'])
      if 'memory_rss_bytes' in process and process['memory_rss_bytes'] is not None:
        point = point.field("memory_rss_bytes", process['memory_rss_bytes'])
      if process['cache_misses'] is not None:
        point = point.field("cache_misses", process['cache_misses'])

      # Add syscall classes as separate fields
      for cls, count in process['syscall_classes'].items():
        point = point.field(f"syscall_{cls}", count)

      write_api.write(bucket=INFLUX_BUCKET, record=point)

    print(f"Written {len(processes)} processes and power={power_watts}W at {timestamp.isoformat()}")
    time.sleep(2)

if __name__ == "__main__":
  smart_meter_client = SmartMeterAPIClient(host=os.getenv("SMARTMETER_HOST"),
                             ssl=False,
                             username=os.getenv("SMARTMETER_USER"),
                             password=os.getenv("SMARTMETER_PASSWORD"))
  monitor_client = MonitoringClient()
  write_metrics(monitor_client, smart_meter_client)