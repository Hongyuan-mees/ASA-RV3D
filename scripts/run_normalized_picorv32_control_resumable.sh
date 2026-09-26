#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

iterations="${1:-100}"
lambda_arch="${2:-1.0}"
lambda_physical="${3:-1.0}"
lambda_timing="${4:-1.0}"

design="picorv32"
scenario="control_datapath_split"
native="results/picorv32_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
features="results/picorv32_features"
area="results/benchmark_summary/picorv32_openroad_instance_area.csv"
timing="results/timing_reports/picorv32_report_checks_max.rpt"

on_dir="results/picorv32_tritonpart_compatible_normalized_dynamic_guarded_repair/control_datapath_split"
off_dir="results/picorv32_tritonpart_compatible_normalized_dynamic_architecture_off_guarded_repair/control_datapath_split"

run_repair() {
  local mode="$1"
  local out_dir="$2"
  local extra_flag=()
  if [[ "${mode}" == "architecture_off" ]]; then
    extra_flag=(--architecture-off)
  fi

  local assignment="${out_dir}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  local summary="${out_dir}/tritonpart_compatible_dynamic_guarded_repair_summary.csv"
  local manifest="${out_dir}/resume_manifest.json"
  local resume_flag=()

  if [[ -s "${summary}" && -s "${assignment}" ]]; then
    echo "== ${mode}: existing summary found, skip repair =="
    return
  fi

  if [[ -s "${manifest}" ]]; then
    echo "== ${mode}: resume from ${manifest} =="
    resume_flag=(--resume-from "${manifest}")
  else
    echo "== ${mode}: start from native assignment =="
  fi

  python3 -u partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py \
    "${extra_flag[@]}" \
    "${resume_flag[@]}" \
    --design "${design}" \
    --scenario "${scenario}" \
    --initial-assignment "${native}" \
    --features-dir "${features}" \
    --instance-area "${area}" \
    --timing-report "${timing}" \
    --max-paths 100 \
    --max-iterations "${iterations}" \
    --max-cut-regret 0.05 \
    --max-pavg-regret 0.0 \
    --max-pwst-delta 0.0 \
    --lambda-arch "${lambda_arch}" \
    --lambda-physical "${lambda_physical}" \
    --lambda-timing "${lambda_timing}" \
    --checkpoint-every 1 \
    --output-dir "${out_dir}"
}

python3 -m py_compile partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py
python3 -m py_compile evaluation/evaluate_architecture_structural_crossing.py

run_repair architecture_on "${on_dir}"
run_repair architecture_off "${off_dir}"

on_assignment="${on_dir}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
off_assignment="${off_dir}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"

echo "== timing crossing =="
python3 evaluation/evaluate_timing_crossing.py \
  --design "${design}" \
  --features-dir "${features}" \
  --timing "${features}/timing_context_scores.csv" \
  --assignment native_timing_aware="${native}" \
  --assignment normalized_architecture_on="${on_assignment}" \
  --assignment normalized_architecture_off="${off_assignment}" \
  --output results/benchmark_summary/picorv32_control_datapath_split_normalized_dynamic_smoke_timing_crossing.csv

echo "== path cuts =="
python3 evaluation/evaluate_timing_path_cuts.py \
  --design "${design}" \
  --timing-report "${timing}" \
  --assignment native_timing_aware="${native}" \
  --assignment normalized_architecture_on="${on_assignment}" \
  --assignment normalized_architecture_off="${off_assignment}" \
  --max-paths 100 \
  --output results/benchmark_summary/picorv32_control_datapath_split_normalized_dynamic_smoke_path_cuts.csv

echo "== structural =="
python3 evaluation/evaluate_architecture_structural_crossing.py \
  --scenario "${scenario}" \
  --native-assignment "${native}" \
  --architecture-off-assignment "${off_assignment}" \
  --architecture-on-assignment "${on_assignment}" \
  --output-prefix results/benchmark_summary/picorv32_control_datapath_split_normalized_structural

echo "== done =="
