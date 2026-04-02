import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import cvxpy as cp
from sklearn.preprocessing import MaxAbsScaler, StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.model_selection import train_test_split

from estimation.linear.cvxpy_optimizer import train_cvxpy_model as optimizer

good_features = [
    "delta_cpu_ns",
    "syscall_count",
    "syscall_class_file",
    "syscall_class_other",
]

target = "interval_energy"
l1_penalty = 0.1
static_penalty = 0.00

df = pd.read_parquet("estimation/data/parallel_bench_replay_1.parquet")
df["_time"] = pd.to_datetime(df["_time"]).dt.round("1ms")
df[good_features] = df[good_features].fillna(0)

interval_energy_all = (
    df[["_time", "interval_energy"]]
    .dropna()
    .drop_duplicates("_time")
    .set_index("_time")["interval_energy"]
)
print(f"Number of intervals with energy: {len(interval_energy_all)}")

df = df[df["_time"].isin(interval_energy_all.index)]
print(f"Process-level rows after filtering: {len(df)}")
print(f"Unique times in process data: {df['_time'].nunique()}")
print(f"Unique times with energy: {interval_energy_all.index.nunique()}")

time_values = interval_energy_all.index.sort_values()
train_times, test_times = train_test_split(time_values, test_size=0.2, shuffle=False)

interval_energy_train = interval_energy_all.loc[train_times]
interval_energy_test = interval_energy_all.loc[test_times]

df_train = df[df["_time"].isin(train_times)].copy()
df_test = df[df["_time"].isin(test_times)].copy()

def train_cvxpy_model(
    df: pd.DataFrame,
    features: list,
    interval_energy: pd.Series,
    l1_penalty=1.0,
    static_penalty=0.0
):
    df = df.copy()
    df["_time"] = pd.to_datetime(df["_time"]).dt.round("1ms")
    df[features] = df[features].fillna(0)
    df = df[df["_time"].isin(interval_energy.index)]
    df = df.sort_values("_time")
    interval_energy = interval_energy.sort_index()

    unmatched = set(df["_time"]) - set(interval_energy.index)
    if unmatched:
        print(f"⚠ Warning: {len(unmatched)} unmatched timestamps in training data.")

    scaler = MaxAbsScaler()
    # scaler = StandardScaler()
    X = scaler.fit_transform(df[features].values)
    time = df["_time"].values

    time_index = np.array(interval_energy.index)
    # np.searchsorted assumes both are sorted and same dtype

    time_index = pd.to_datetime(interval_energy.index).values.astype('datetime64[ns]')
    time = pd.to_datetime(df["_time"]).values.astype('datetime64[ns]')
    interval_idx = np.searchsorted(time_index, time)

    n_intervals = len(interval_energy)
    n_samples = len(df)
    A = np.zeros((n_intervals, n_samples))
    for i, idx in enumerate(interval_idx):
        A[idx, i] = 1

    w = cp.Variable(X.shape[1])
    s = cp.Variable()  # static component

    preds = X @ w
    interval_preds = A @ preds + s
    loss = cp.sum_squares(interval_preds - interval_energy.values)
    reg = l1_penalty * cp.norm1(w) + static_penalty * cp.abs(s)
    prob = cp.Problem(cp.Minimize(loss + reg), constraints=[s >= 0, w >= 0])
    prob.solve()

    return {
        "weights": w.value,
        "static_energy": s.value,
        "scaler": scaler
    }

results = train_cvxpy_model(df_train, good_features, interval_energy_train, l1_penalty, static_penalty)
# results = optimizer(df_train, good_features, interval_energy_train)
weights = results["weights"]
static_energy = results["static_energy"]
scaler = results["scaler"]

print("Learned weights:")
for f, w in zip(good_features, weights):
    print(f"  {f}: {w:.4e}")
print(f"Static energy component: {static_energy:.4f}")

def predict_per_interval(df, weights, scaler, good_features, static_energy):
    df_scaled = df.copy()
    df_scaled[good_features] = scaler.transform(df_scaled[good_features])
    df_scaled["predicted_process_energy"] = df_scaled[good_features].values @ weights
    pred = df_scaled.groupby("_time")["predicted_process_energy"].sum().reset_index()
    return pred

df_pred = predict_per_interval(df_test, weights, scaler, good_features, static_energy)
df_pred = df_pred.merge(
    interval_energy_test.rename("interval_energy"),
    left_on="_time", right_index=True
)
df_pred["predicted_total_energy"] = df_pred["predicted_process_energy"] + static_energy

r2 = r2_score(df_pred["interval_energy"], df_pred["predicted_total_energy"])
mae = mean_absolute_error(df_pred["interval_energy"], df_pred["predicted_total_energy"])
mean_energy = df_pred["interval_energy"].mean()
print(f"\nR² (interval-level): {r2:.4f}")
print(f"MAE (interval-level): {mae:.4f}")
print(f"Mean interval energy: {mean_energy:.4f}")
print(f"MAE (% of mean): {100 * mae / mean_energy:.2f}%")

plt.figure(figsize=(14, 6))
plt.plot(df_pred["_time"], df_pred["interval_energy"], label="Actual Energy", linewidth=4.5)
plt.plot(df_pred["_time"], df_pred["predicted_total_energy"], label="Predicted Energy", linestyle="--", linewidth=4.5)
plt.xlabel("Time")
plt.ylabel("Interval Energy")
plt.title("Actual vs Predicted Total Interval Energy")
plt.legend()
plt.tight_layout()
plt.show()

plt.figure(figsize=(14, 4))
plt.plot(df_pred["_time"], df_pred["interval_energy"] - df_pred["predicted_total_energy"], label="Error")
plt.axhline(0, color="gray", linestyle="--")
plt.ylabel("Prediction Error")
plt.xlabel("Time")
plt.title("Prediction Error Over Time")
plt.tight_layout()
plt.show()

plt.figure(figsize=(10, 4))
plt.hist(df_pred["interval_energy"] - df_pred["predicted_total_energy"], bins=40)
plt.title("Histogram of Prediction Errors")
plt.xlabel("Error")
plt.ylabel("Count")
plt.tight_layout()
plt.show()

df_test_plot = df_test.copy()
df_test_plot[good_features] = scaler.transform(df_test_plot[good_features])
df_test_plot["estimated_process_energy"] = df_test_plot[good_features].values @ weights

agg = (
    df_test_plot
    .groupby(["_time", "pid"])["estimated_process_energy"]
    .sum()
    .reset_index()
)

pivot = agg.pivot(index="_time", columns="pid", values="estimated_process_energy").fillna(0)

N = 8
top_processes = pivot.sum().sort_values(ascending=False).head(N).index
pivot_top = pivot[top_processes]

if len(pivot.columns) > N:
    pivot_top["Other"] = pivot.drop(columns=top_processes).sum(axis=1)

print((pivot_top < 0).sum())
print("Fraction of intervals with negative values per process:")
print((pivot_top < 0).mean())

plt.figure(figsize=(16, 7))
pivot_top_clipped = pivot_top.clip(lower=0)
pivot_top_clipped.plot.area(figsize=(16, 7), alpha=0.8)
plt.xlabel("Time")
plt.ylabel("Estimated Process Energy per Interval")
plt.title(f"Estimated Per-Process Energy Contributions per Interval (Top {N}, Clipped at 0)")
plt.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0))
plt.tight_layout()
plt.show()


