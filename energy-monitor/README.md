# Per-Process Energy Estimation

This project uses the **Phoronix Test Suite** to generate realistic workloads on a server and collect system metrics for per-process energy estimation using linear regression.

---

## Phoronix Test Suite Installation

```bash
# Clone the repository
git clone https://github.com/phoronix-test-suite/phoronix-test-suite

# Run the install script for your operating system
# Linux:
./phoronix-test-suite/install-sh

# macOS:
./phoronix-test-suite/install_macos

# Windows:
install.bat
```

---
## Benchmark Installation
```bash
# Run the install script
./install_benchmarks.sh
```
---

## Batch Mode Configuration

Before running automated benchmarks, configure Phoronix for non-interactive batch mode:

```bash
phoronix-test-suite batch-setup
```

### Recommended Configuration:

```
Save test results when in batch mode (Y/n): Y
Open the web browser automatically when in batch mode (y/N): N
Auto upload the results to OpenBenchmarking.org (Y/n): N
Prompt for test identifier (Y/n): N
Prompt for test description (Y/n): N
Prompt for saved results file-name (Y/n): N
Run all test options (Y/n): Y
```

---

## Running the benchmark


## BPF Installation

```bash
sudo apt-get install bpfcc-tools linux-headers-$(uname -r)
```

> Optional: See the [BPF installation guide](https://example.com) for more details.

---

## Perf Installation

```bash
sudo apt-get install linux-tools-common linux-tools-generic linux-tools-$(uname -r)
```

## Running the Montitoring Script

### Required Python packages
Install the following packages
-    pandas
-    numpy
-    psutil
-    influxdb-client
-    requests
-    pyyaml
-    optional:
-    cvxpy      # only for model training
-    scikit-learn  # feature/model workflows
-    matplotlib    # plots


### Environment variables (optional)
You can provide Influx and smart meter settings via environment variables:
- `INFLUX_URL`
- `INFLUX_TOKEN`
- `INFLUX_ORG`
- `INFLUX_BUCKET`
- `SMARTMETER_HOST`
- `SMARTMETER_USER`
- `SMARTMETER_PASSWORD`

Sensitive values (like `INFLUX_TOKEN`) can be supplied via environment variables instead of the CLI.

### CLI options for `delta_aggregator.py`
Important flags supported by the script:
- `--influx-url` (falls back to `INFLUX_URL`, default `http://localhost:8086`)
- `--influx-token` (falls back to `INFLUX_TOKEN`)
- `--influx-org` (falls back to `INFLUX_ORG`)
- `--influx-bucket` (falls back to `INFLUX_BUCKET`)
- `--interval` (float, aggregation window in seconds; default `2.0`)
- `--sample-rate` (float, optional; if omitted it defaults to the same value as `--interval`)
- `--meter-host`, `--meter-user`, `--meter-password`, `--meter-ssl`, `--meter-sensor-id`

Notes:
- If `--sample-rate` is omitted, sampling frequency will be set equal to `--interval`.
- Use environment variables for secrets where possible.

### Running the monitor

1. Example using environment variables in PowerShell:

    $Env:INFLUX_URL = "http://influx:8086"
    $Env:INFLUX_TOKEN = "your-token"
    $Env:INFLUX_ORG = "myorg"
    $Env:INFLUX_BUCKET = "mybucket"

    python .\delta_aggregator.py --interval 2

2. Example passing values on the command line (sample-rate omitted, so it equals interval):

    python .\delta_aggregator.py `
      --influx-url "http://influx:8086" `
      --influx-token "your-token" `
      --influx-org "myorg" `
      --influx-bucket "mybucket" `
      --interval 2

3. Example with explicit `--sample-rate`:

    python .\delta_aggregator.py --interval 2 --sample-rate 0.5

Stop the monitor with `Ctrl+C`. The script attempts a clean shutdown and closes the DB client.

## Data Loader

The `data_loader.py` script can be used to load the collected data from InfluxDB for analysis and model training.
### Options for `data_loader.py`
Unfortunatly, the script and the corresponding query are currently hardcoded as the application is a prototype to research possibilities in per process energy decomposition. The script can be modified to fit your needs.
The influx connection parameters need to be filled in the corresponding variables. 
The influx query can be modified in the method in the DBClient class.
The file output path need to be modified.
After that, the file can be used for further analysis and model training.


## Feature selection
Feature selection can be done using the estimation/feature_selection/feature_selection.py script. The script uses a random forest model to estimate feature importance. The data input path can be modified in the script.
The script will return different metrics and plots to determine feature importance, such as correlation.

## Shared model
The shared model can be found in the estimation/share_estimator.py script.
It returns a plot with the estimated power.

## Regression model
The regression model can be found in the estimation/cvxpy_estimator.py script.
It takes an data input path and returns some evaluation metrics.
