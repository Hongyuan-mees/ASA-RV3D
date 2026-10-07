#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

scenario_filter="${1:-all}"
design="scr1_core_tuned"
scenarios=(control_datapath_split memory_near_logic state_and_clock_protected)

native="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
features="results/${design}_features"
timing_report="results/timing_reports/${design}_report_checks_max.rpt"

echo "== reviewer SCR1 restored-baseline canonical evaluation =="
echo "repo_root=${repo_root}"
echo "scenario_filter=${scenario_filter}"

python3 -m py_compile \
  evaluation/evaluate_timing_crossing.py \
  evaluation/evaluate_timing_path_cuts.py \
  evaluation/evaluate_architecture_structural_crossing.py \
  scripts/summarize_reviewer_scr1_restored_phase3.py

for scenario in "${scenarios[@]}"; do
  if [[ "${scenario_filter}" != "all" && "${scenario_filter}" != "${scenario}" ]]; then
    continue
  fi

  on_assignment="results/${design}_tritonpart_compatible_normalized_dynamic_reviewer_restored_baseline_guarded_repair/${scenario}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  off_assignment="results/${design}_tritonpart_compatible_normalized_dynamic_reviewer_restored_baseline_architecture_off_guarded_repair/${scenario}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  timing_out="results/benchmark_summary/${design}_${scenario}_reviewer_restored_baseline_timing_crossing.csv"
  path_out="results/benchmark_summary/${design}_${scenario}_reviewer_restored_baseline_path_cuts.csv"
  structural_prefix="results/benchmark_summary/${design}_${scenario}_reviewer_restored_baseline_structural"

  echo
  echo "===== ${design} / ${scenario} / reviewer restored baseline ====="
  for required in "${native}" "${on_assignment}" "${off_assignment}" "${features}/timing_context_scores.csv" "${timing_report}"; do
    if [[ ! -s "${required}" ]]; then
      echo "missing required input: ${required}" >&2
      exit 2
    fi
  done

  echo "== timing crossing =="
  python3 evaluation/evaluate_timing_crossing.py \
    --design "${design}" \
    --features-dir "${features}" \
    --timing "${features}/timing_context_scores.csv" \
    --assignment "native_timing_aware=${native}" \
    --assignment "reviewer_restored_architecture_on=${on_assignment}" \
    --assignment "reviewer_restored_architecture_off=${off_assignment}" \
    --output "${timing_out}"

  echo "== path cuts =="
  python3 evaluation/evaluate_timing_path_cuts.py \
    --design "${design}" \
    --timing-report "${timing_report}" \
    --assignment "native_timing_aware=${native}" \
    --assignment "reviewer_restored_architecture_on=${on_assignment}" \
    --assignment "reviewer_restored_architecture_off=${off_assignment}" \
    --max-paths 100 \
    --output "${path_out}"

  echo "== structural =="
  python3 evaluation/evaluate_architecture_structural_crossing.py \
    --scenario "${scenario}" \
    --native-assignment "${native}" \
    --architecture-off-assignment "${off_assignment}" \
    --architecture-on-assignment "${on_assignment}" \
    --output-prefix "${structural_prefix}"
done

echo
echo "== reviewer SCR1 restored-baseline summary =="
python3 scripts/summarize_reviewer_scr1_restored_phase3.py

echo
echo "== outputs =="
echo "results/benchmark_summary/reviewer_scr1_restored_phase3_summary.csv"
echo "results/benchmark_summary/reviewer_scr1_restored_phase3_rollup.csv"
find results/benchmark_summary \
  \( -name "scr1_core_tuned_*_reviewer_restored_baseline_timing_crossing.csv" \
  -o -name "scr1_core_tuned_*_reviewer_restored_baseline_path_cuts.csv" \
  -o -name "scr1_core_tuned_*_reviewer_restored_baseline_structural_summary.csv" \
  -o -name "scr1_core_tuned_*_reviewer_restored_baseline_structural_rollup.csv" \) | sort
