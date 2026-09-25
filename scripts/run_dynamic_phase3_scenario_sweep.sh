#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_root"

designs=("$@")
if [ "$#" -eq 0 ]; then
  designs=(picorv32 riscv32i)
fi

scenarios=(
  control_datapath_split
  memory_near_logic
  state_and_clock_protected
)

budget_for_design() {
  case "$1" in
    picorv32) echo 200 ;;
    riscv32i) echo 50 ;;
    *) echo 50 ;;
  esac
}

for design in "${designs[@]}"; do
  max_iterations="$(budget_for_design "$design")"
  for scenario in "${scenarios[@]}"; do
    echo
    echo "===== dynamic Phase-3: ${design} / ${scenario} / ${max_iterations} iterations ====="
    initial_assignment="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
    features_dir="results/${design}_features"
    instance_area="results/benchmark_summary/${design}_openroad_instance_area.csv"
    timing_report="results/timing_reports/${design}_report_checks_max.rpt"
    repair_dir="results/${design}_tritonpart_compatible_dynamic_guarded_repair/${scenario}"
    trace="${repair_dir}/tritonpart_compatible_dynamic_guarded_repair_trace.csv"

    python3 -u partition/partition_tritonpart_compatible_dynamic_guarded_repair.py \
      --design "$design" \
      --scenario "$scenario" \
      --initial-assignment "$initial_assignment" \
      --features-dir "$features_dir" \
      --instance-area "$instance_area" \
      --timing-report "$timing_report" \
      --max-paths 100 \
      --max-iterations "$max_iterations" \
      --max-cut-regret 0.05 \
      --max-pavg-regret 0.0 \
      --max-pwst-delta 0.0 \
      --progress-every-candidates 500 \
      --output-dir "$repair_dir"

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
      --output-dir "results/${design}_tritonpart_compatible_dynamic_canonical_checkpoint/${scenario}"

    selected_assignment="results/${design}_tritonpart_compatible_dynamic_canonical_checkpoint/${scenario}/dynamic_canonical_selected_checkpoint_assignment.csv"
    python3 evaluation/evaluate_timing_crossing.py \
      --design "$design" \
      --features-dir "$features_dir" \
      --timing "${features_dir}/timing_context_scores.csv" \
      --assignment "native_timing_aware=${initial_assignment}" \
      --assignment "dynamic_canonical_checkpoint=${selected_assignment}" \
      --output "results/benchmark_summary/${design}_${scenario}_dynamic_canonical_checkpoint_timing_crossing.csv"

    python3 evaluation/evaluate_timing_path_cuts.py \
      --design "$design" \
      --timing-report "$timing_report" \
      --assignment "native_timing_aware=${initial_assignment}" \
      --assignment "dynamic_canonical_checkpoint=${selected_assignment}" \
      --max-paths 100 \
      --output "results/benchmark_summary/${design}_${scenario}_dynamic_canonical_checkpoint_path_cuts.csv"
  done
done

python3 scripts/summarize_dynamic_constrained_asa_phase3_scenarios.py

echo
echo "===== dynamic Phase-3 scenario sweep rollup ====="
cat results/benchmark_summary/dynamic_constrained_asa_phase3_scenario_rollup.csv
