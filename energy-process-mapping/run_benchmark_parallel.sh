#!/bin/bash

# Benchmark groups
cpu_benchmarks=(
  "pts/build-linux-kernel" "pts/compress-7zip" "pts/x264"
  "pts/blake2" "pts/coremark" "pts/c-ray" "pts/gmpbench" "pts/primesieve"
)

mem_benchmarks=(
  "pts/stream" "pts/mbw" "pts/tinymembench" "pts/pmbench"
)

io_benchmarks=(
  "pts/dbench" "pts/compilebench" "pts/fs-mark" "pts/postmark"
)

server_benchmarks=(
  "pts/apache" "pts/memcached" "pts/redis" "pts/mysqlslap" "pts/cassandra" "pts/nginx"
)

mixed_benchmarks=(
  "pts/sysbench" "pts/stress-ng" "pts/byte" "pts/hackbench"
)

all_benchmarks=("${cpu_benchmarks[@]}" "${mem_benchmarks[@]}" "${io_benchmarks[@]}" "${server_benchmarks[@]}" "${mixed_benchmarks[@]}")

iterations=30
min_parallel=4      # Minimum benchmarks to run in parallel
max_parallel=6      # Maximum benchmarks to run in parallel
bench_timeout_min=2  # Timeout for each benchmark (e.g. 10m for 10 minutes)
bench_timeout_max=3   # Timeout for each benchmark (e.g. 10m for 10 minutes)
min_idle=0.2        # Min idle time in minutes (e.g., 30 seconds)
max_idle=0.5          # Max idle time in minutes

run_benchmark() {
  bench="$1"
  safe_name=$(echo "$bench" | tr '/' '_')
  echo "[$(date)] ▶ Running: $bench"

  # timeout forcibly kills the process after $bench_timeout
  timeout_seconds=$(awk "BEGIN {print int(($RANDOM/32767)*($bench_timeout_max-$bench_timeout_min)*60 + ($bench_timeout_min*60))}")
  timeout "$timeout_seconds" phoronix-test-suite batch-run "$bench" \
    --force-all-threads \
    -y \
    > "/tmp/pts_${safe_name}.log" 2>&1

  result=$?
  if [[ $result -eq 124 ]]; then
    echo "[$(date)] ⏰ Timed out: $bench"
  else
    echo "[$(date)] ✔ Finished: $bench"
  fi
}

for ((i=1; i<=iterations; i++)); do
  echo "[$(date)] 🌀 Iteration $i"

  # Ensure at least min_parallel, up to max_parallel
  count=$(( RANDOM % (max_parallel - min_parallel + 1) + min_parallel ))
  selected=()
  for ((j=0; j<count; j++)); do
    selected+=("${all_benchmarks[$RANDOM % ${#all_benchmarks[@]}]}")
  done

  echo "[$(date)] Selected benchmarks: ${selected[*]}"

  for bench in "${selected[@]}"; do
    run_benchmark "$bench" &
  done

  wait

  # Lower random idle time
  idle_seconds=$(awk "BEGIN {print int(($RANDOM/32767)*($max_idle-$min_idle)*60 + ($min_idle*60))}")
  echo "[$(date)] 💤 Sleeping $(awk "BEGIN {print $idle_seconds/60}") minutes..."
  sleep "$idle_seconds"
done

echo "✅ All iterations completed."
