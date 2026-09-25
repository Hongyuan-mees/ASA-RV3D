#!/usr/bin/env bash
set -euo pipefail

design="${1:?usage: bash scripts/run_dynamic_canonical_checkpoint_selection.sh <design> <scenario>}"
scenario="${2:?usage: bash scripts/run_dynamic_canonical_checkpoint_selection.sh <design> <scenario>}"

repo_root="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_root"

dynamic_dir="results/${design}_tritonpart_compatible_dynamic_guarded_repair/${scenario}"
trace="${dynamic_dir}/tritonpart_compatible_dynamic_guarded_repair_trace.csv"
initial_assignment="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
features_dir="results/${design}_features"
instance_area="results/benchmark_summary/${design}_openroad_instance_area.csv"
timing_report="results/timing_reports/${design}_report_checks_max.rpt"
checkpoint_dir="results/${design}_tritonpart_compatible_dynamic_canonical_checkpoint/${scenario}"
selected_assignment="${checkpoint_dir}/dynamic_canonical_selected_checkpoint_assignment.csv"
timing_crossing_out="results/benchmark_summary/${design}_${scenario}_dynamic_canonical_checkpoint_timing_crossing.csv"
path_cuts_out="results/benchmark_summary/${design}_${scenario}_dynamic_canonical_checkpoint_path_cuts.csv"

echo "== select canonical timing-safe checkpoint =="
python3 scripts/select_dynamic_checkpoint_with_canonical_timing.py \
  --design "$design" \
  --scenario "$scenario" \
  --initial-assignment "$initial_assignment" \
  --features-dir "$features_dir" \
  --instance-area "$instance_area" \
  --timing-report "$timing_report" \
  --trace "$trace" \
  --max-paths 100 \
  --max-cut-regret 0.05 \
  --max-timing-weighted-regret 0.0 \
  --output-dir "$checkpoint_dir"

echo
echo "== independent timing crossing for selected =="
python3 evaluation/evaluate_timing_crossing.py \
  --design "$design" \
  --features-dir "$features_dir" \
  --timing "${features_dir}/timing_context_scores.csv" \
  --assignment "native_timing_aware=${initial_assignment}" \
  --assignment "dynamic_canonical_checkpoint=${selected_assignment}" \
  --output "$timing_crossing_out"

echo
echo "== independent path cuts for selected =="
python3 evaluation/evaluate_timing_path_cuts.py \
  --design "$design" \
  --timing-report "$timing_report" \
  --assignment "native_timing_aware=${initial_assignment}" \
  --assignment "dynamic_canonical_checkpoint=${selected_assignment}" \
  --max-paths 100 \
  --output "$path_cuts_out"

echo
echo "== canonical selected checkpoint =="
cat "${checkpoint_dir}/dynamic_canonical_selected_checkpoint.csv"

echo
echo "== timing crossing =="
cat "$timing_crossing_out"

echo
echo "== path cuts =="
cat "$path_cuts_out"
