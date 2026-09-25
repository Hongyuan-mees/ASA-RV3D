#!/usr/bin/env bash
set -euo pipefail

design="${1:-picorv32}"
scenario="${2:-state_and_clock_protected}"

native_assignment="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
features_dir="results/${design}_features"
trace="results/${design}_timing_aware_start_asa/${scenario}/local_refinement_trace.csv"
replay_dir="results/${design}_asa_on_native_cut_regret_replay/${scenario}"
replay_summary="results/benchmark_summary/asa_on_native_${design}_${scenario}_cut_regret_replay_summary.csv"
eval_csv="results/benchmark_summary/asa_on_native_${design}_${scenario}_cut_regret_replay_eval.csv"
timing_report="results/timing_reports/${design}_report_checks_max.rpt"

echo "== ASA-on-native bounded-regret Phase 1 =="
echo "design=${design}"
echo "scenario=${scenario}"

python3 scripts/run_timing_aware_start_experiments.py \
  --design "${design}" \
  --scenario "${scenario}"

python3 scripts/replay_asa_on_native_cut_regret.py \
  --design "${design}" \
  --scenario "${scenario}" \
  --initial-assignment "${native_assignment}" \
  --trace "${trace}" \
  --features-dir "${features_dir}" \
  --output-dir "${replay_dir}" \
  --output-summary "${replay_summary}"

python3 evaluation/evaluate_asa_on_native_cut_regret_replay.py \
  --design "${design}" \
  --scenario "${scenario}" \
  --replay-summary "${replay_summary}" \
  --native-assignment "${native_assignment}" \
  --timing-report "${timing_report}" \
  --features-dir "${features_dir}" \
  --output "${eval_csv}"

echo
echo "== outputs =="
echo "${replay_summary}"
echo "${eval_csv}"
cat "${eval_csv}"

