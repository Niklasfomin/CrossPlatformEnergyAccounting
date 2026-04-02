import time
import threading
from collections import deque

SMART_METER_ID = "L1"

def get_gude_active_power(client, meter_id=SMART_METER_ID):
  status_json = client.get_status_json()
  for entry in status_json:
    if entry.get("id") == meter_id:
      data = entry["data"]
      return data["ActivePower"]
  raise ValueError(f"Meter id {meter_id} not found in smart meter status.json")


class PowerSampler(threading.Thread):
  def __init__(self, smart_meter_client, interval=1.0, sample_rate=0.3):
    super().__init__(daemon=True)
    self.client = smart_meter_client
    self.sample_rate = sample_rate
    self.samples = deque()
    self.lock = threading.Lock()
    self.running = False

  def run(self):
    self.running = True
    while self.running:
      now = time.time()
      try:
        p = get_gude_active_power(self.client)
      except Exception as e:
        p = None
      with self.lock:
        self.samples.append((now, p))
        # Keep samples for at least 2 intervals to allow flexibility
        while self.samples and now - self.samples[0][0] > 3 * self.sample_rate * 50:
          self.samples.popleft()
      time.sleep(self.sample_rate)

  def stop(self):
    self.running = False

  def get_samples(self, start_time, end_time):
    with self.lock:
      return [(t, p) for (t, p) in list(self.samples) if start_time <= t <= end_time]