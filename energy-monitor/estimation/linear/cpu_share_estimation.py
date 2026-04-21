import pandas as pd
import numpy as np

class CpuShareEnergyEstimator:
    def __init__(self, cpu_col="delta_cpu_ns", energy_col="interval_energy", time_col="_time", idle_threshold=1e6):
        """
        Parameters:
            cpu_col: str - column representing CPU usage per process
            energy_col: str - column representing total interval energy
            time_col: str - column representing the timestamp or time interval
            idle_threshold: float - max total CPU usage allowed to consider an interval 'idle'
        """
        self.cpu_col = cpu_col
        self.energy_col = energy_col
        self.time_col = time_col
        self.idle_threshold = idle_threshold
        self.static_energy = None

    def estimate_static_energy(self, df):
        """
        Estimate static (baseline) energy from nearly idle time intervals.
        """
        # cpu_sum_per_time = df.groupby(self.time_col)[self.cpu_col].sum()
        # idle_times = cpu_sum_per_time[cpu_sum_per_time < self.idle_threshold].index
        #
        # static_df = df[df[self.time_col].isin(idle_times)]
        # if static_df.empty:
        #     raise ValueError("No idle intervals found under threshold. Cannot estimate static energy.")


        self.static_energy = df["interval_energy"].min()
        print("Estimated static energy:", self.static_energy)
        return self.static_energy

    def compute_process_energy(self, df):
        """
        Compute per-process energy by subtracting static energy and allocating dynamic energy
        based on CPU usage proportion.
        Returns a DataFrame with an additional column: 'process_energy'
        """
        if self.static_energy is None:
            raise ValueError("Static energy not estimated. Call estimate_static_energy() first.")

        # Compute total CPU usage per time window
        cpu_sum_per_time = df.groupby(self.time_col)[self.cpu_col].transform("sum")

        # Avoid division by zero
        cpu_sum_per_time = cpu_sum_per_time.replace(0, np.nan)

        # Estimate dynamic energy (interval energy - static energy)
        df["dynamic_energy"] = df[self.energy_col] - self.static_energy

        # Compute per-process energy contribution
        df["process_energy"] = (df[self.cpu_col] / cpu_sum_per_time) * df["dynamic_energy"]

        # Replace NaNs (where CPU usage was 0 for all processes) with 0
        df["process_energy"] = df["process_energy"].fillna(0.0)

        return df

    def apply(self, df):
        """
        Full pipeline: estimate static energy and compute per-process energy.
        """
        self.estimate_static_energy(df)
        return self.compute_process_energy(df)