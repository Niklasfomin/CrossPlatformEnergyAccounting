import argparse
import os
from typing import List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

KNOWN_PARSEABLE_COLUMNS = [
    "task_id",
    "status",
    "name",
    "energy_consumption",
    "CO2e",
    "CO2e_market",
    "carbon_intensity",
    "%cpu",
    "memory",
    "realtime",
    "cpus",
    "powerdraw_cpu",
    "cpu_model",
    "raw_energy_processor",
    "raw_energy_memory",
]


def detect_file_type(file_path: str) -> str:
    """Detect the file type from the file extension."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == ".csv":
        return "csv"
    if ext in (".xlsx", ".xls"):
        return "excel"
    if ext == ".json":
        return "json"
    if ext == ".txt":
        return "text"

    raise ValueError(f"Unsupported file type: {ext}")


def load_trace_data(file_path: str) -> pd.DataFrame:
    """Load a trace file into a pandas DataFrame."""
    file_type = detect_file_type(file_path)

    if file_type == "text":
        return pd.read_csv(file_path, sep="\t", engine="python")

    if file_type == "csv":
        return pd.read_csv(file_path)

    if file_type == "excel":
        return pd.read_excel(file_path)

    if file_type == "json":
        return pd.read_json(file_path, lines=True)

    raise ValueError(f"Unsupported file type: {file_type}")


def discover_parseable_columns(file_path: str) -> List[str]:
    """Inspect the file format and return columns that can be parsed."""
    file_type = detect_file_type(file_path)

    if file_type == "csv":
        df = pd.read_csv(file_path, nrows=0)
        return list(df.columns)

    if file_type == "excel":
        df = pd.read_excel(file_path, nrows=0)
        return list(df.columns)

    if file_type == "json":
        df = pd.read_json(file_path, lines=True, nrows=0)
        return list(df.columns)

    if file_type == "text":
        df = pd.read_csv(file_path, sep="\t", engine="python", nrows=0)
        columns = list(df.columns)

        if columns:
            return [col for col in KNOWN_PARSEABLE_COLUMNS if col in columns]

        return []

    return []

    def plot_selected_column(file_path: str, column: str) -> None:
        """Create and save a simple line plot for one selected column."""
        df = load_trace_data(file_path)

        if column not in df.columns:
            raise ValueError(f"Column '{column}' was not found in the file.")

        series = pd.to_numeric(df[column], errors="coerce")

        plots_dir = os.path.join(os.path.dirname(file_path), "plots")
        os.makedirs(plots_dir, exist_ok=True)

        fig, ax = plt.subplots()
        ax.plot(series.index, series, marker="o")
        ax.set_title(column)
        ax.set_xlabel("Row")
        ax.set_ylabel(column)
        fig.tight_layout()

        output_path = os.path.join(plots_dir, f"{column}.png")
        if os.path.exists(output_path):
            base, ext = os.path.splitext(output_path)
            suffix = 1
            while os.path.exists(f"{base}_{suffix}{ext}"):
                suffix += 1
            output_path = f"{base}_{suffix}{ext}"

        fig.savefig(output_path)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a trace file, report parseable columns, and plot selected ones."
    )
    parser.add_argument("file_path", help="Path to the input file")
    parser.add_argument(
        "--plot",
        help="Column to plot. If omitted, only parseable columns are printed.",
    )
    args = parser.parse_args()

    columns = discover_parseable_columns(args.file_path)

    print(f"Detected file type: {detect_file_type(args.file_path)}")
    print("Parseable columns:")
    for column in columns:
        print(column)

    if args.plot:
        plot_selected_column(args.file_path, args.plot)


if __name__ == "__main__":
    main()
