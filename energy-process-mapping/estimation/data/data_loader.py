from database.DBClient import DBClient
import pandas as pd

INFLUX_URL = ""
INFLUX_TOKEN = ""
INFLUX_ORG = ""
INFLUX_BUCKET = ""

data_client = DBClient(INFLUX_URL,INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET)
df = data_client.load_data()

print(f"Loaded {len(df)} rows from InfluxDB")

active = df[df["interval_energy"] > 0]
print(f"Intervall energy shape: {active.shape}")

print("Memory usage (MB):", df.memory_usage(deep=True).sum() / 1e6)
df.to_parquet("parallel_bench_replay_2.parquet")