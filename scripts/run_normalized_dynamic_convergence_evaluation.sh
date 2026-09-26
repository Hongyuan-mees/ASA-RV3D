#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

design_filter="${1:-all}"
scenario_filter="${2:-all}"

cases=(
  "picorv32 control_datapath_split"
  "picorv32 memory_near_logic"
  "picorv32 state_and_clock_protected"
  "riscv32i control_datapath_split"
  "riscv32i memory_near_logic"
  "riscv32i state_and_clock_protected"
)

echo "== normalized dynamic convergence canonical evaluation =="
echo "repo_root=${repo_root}"
echo "design_filter=${design_filter}"
echo "scenario_filter=${scenario_filter}"

python3 -m py_compile \
  evaluation/evaluate_timing_crossing.py \
  evaluation/evaluate_timing_path_cuts.py \
  evaluation/evaluate_architecture_structural_crossing.py

for item in "${cases[@]}"; do
  read -r design scenario <<<"${item}"
  if [[ "${design_filter}" != "all" && "${design_filter}" != "${design}" ]]; then
    continue
  fi
  if [[ "${scenario_filter}" != "all" && "${scenario_filter}" != "${scenario}" ]]; then
    continue
  fi

  native="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
  features="results/${design}_features"
  timing_report="results/timing_reports/${design}_report_checks_max.rpt"
  on_assignment="results/${design}_tritonpart_compatible_normalized_dynamic_convergence_guarded_repair/${scenario}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  off_assignment="results/${design}_tritonpart_compatible_normalized_dynamic_convergence_architecture_off_guarded_repair/${scenario}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  timing_out="results/benchmark_summary/${design}_${scenario}_normalized_dynamic_convergence_timing_crossing.csv"
  path_out="results/benchmark_summary/${design}_${scenario}_normalized_dynamic_convergence_path_cuts.csv"
  structural_prefix="results/benchmark_summary/${design}_${scenario}_normalized_dynamic_convergence_structural"

  echo
  echo "===== ${design} / ${scenario} ====="

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
    --assignment "normalized_convergence_architecture_on=${on_assignment}" \
    --assignment "normalized_convergence_architecture_off=${off_assignment}" \
    --output "${timing_out}"

  echo "== path cuts =="
  python3 evaluation/evaluate_timing_path_cuts.py \
    --design "${design}" \
    --timing-report "${timing_report}" \
    --assignment "native_timing_aware=${native}" \
    --assignment "normalized_convergence_architecture_on=${on_assignment}" \
    --assignment "normalized_convergence_architecture_off=${off_assignment}" \
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
echo "== canonical convergence evaluation outputs =="
find results/benchmark_summary \
  \( -name "*normalized_dynamic_convergence_timing_crossing.csv" \
  -o -name "*normalized_dynamic_convergence_path_cuts.csv" \
  -o -name "*normalized_dynamic_convergence_structural_summary.csv" \
  -o -name "*normalized_dynamic_convergence_structural_rollup.csv" \) | sort
