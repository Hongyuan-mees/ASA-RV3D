#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

iterations="${1:-100}"
lambda_arch="${2:-1.0}"
lambda_physical="${3:-1.0}"
lambda_timing="${4:-1.0}"

cases=(
  "picorv32 state_and_clock_protected"
  "riscv32i control_datapath_split"
)

echo "== normalized dynamic Phase-3 smoke =="
echo "repo_root=${repo_root}"
echo "iterations=${iterations}"
echo "lambda_arch=${lambda_arch}"
echo "lambda_physical=${lambda_physical}"
echo "lambda_timing=${lambda_timing}"

for item in "${cases[@]}"; do
  read -r design scenario <<<"${item}"

  native_assignment="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
  features_dir="results/${design}_features"
  timing_report="results/timing_reports/${design}_report_checks_max.rpt"
  area_csv="results/benchmark_summary/${design}_openroad_instance_area.csv"
  on_dir="results/${design}_tritonpart_compatible_normalized_dynamic_guarded_repair/${scenario}"
  off_dir="results/${design}_tritonpart_compatible_normalized_dynamic_architecture_off_guarded_repair/${scenario}"

  echo
  echo "===== normalized smoke: ${design} / ${scenario} ====="

  if [[ ! -s "${native_assignment}" ]]; then
    echo "missing native assignment: ${native_assignment}" >&2
    exit 2
  fi
  if [[ ! -s "${area_csv}" ]]; then
    echo "missing area csv: ${area_csv}" >&2
    echo "Run the existing OpenROAD area extraction first, or reuse a completed Phase-3 run that generated this CSV." >&2
    exit 2
  fi

  rm -rf "${on_dir}" "${off_dir}"

  echo
  echo "== normalized architecture ON =="
  python3 -u partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py \
    --design "${design}" \
    --scenario "${scenario}" \
    --initial-assignment "${native_assignment}" \
    --features-dir "${features_dir}" \
    --instance-area "${area_csv}" \
    --timing-report "${timing_report}" \
    --max-paths 100 \
    --max-iterations "${iterations}" \
    --max-cut-regret 0.05 \
    --max-pavg-regret 0.0 \
    --max-pwst-delta 0.0 \
    --lambda-arch "${lambda_arch}" \
    --lambda-physical "${lambda_physical}" \
    --lambda-timing "${lambda_timing}" \
    --progress-every-candidates 1000 \
    --output-dir "${on_dir}"

  echo
  echo "== normalized architecture OFF =="
  python3 -u partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py \
    --architecture-off \
    --design "${design}" \
    --scenario "${scenario}" \
    --initial-assignment "${native_assignment}" \
    --features-dir "${features_dir}" \
    --instance-area "${area_csv}" \
    --timing-report "${timing_report}" \
    --max-paths 100 \
    --max-iterations "${iterations}" \
    --max-cut-regret 0.05 \
    --max-pavg-regret 0.0 \
    --max-pwst-delta 0.0 \
    --lambda-arch "${lambda_arch}" \
    --lambda-physical "${lambda_physical}" \
    --lambda-timing "${lambda_timing}" \
    --progress-every-candidates 1000 \
    --output-dir "${off_dir}"

  on_assignment="${on_dir}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  off_assignment="${off_dir}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  timing_out="results/benchmark_summary/${design}_${scenario}_normalized_dynamic_smoke_timing_crossing.csv"
  path_out="results/benchmark_summary/${design}_${scenario}_normalized_dynamic_smoke_path_cuts.csv"

  echo
  echo "== normalized timing crossing =="
  python3 evaluation/evaluate_timing_crossing.py \
    --design "${design}" \
    --features-dir "${features_dir}" \
    --timing "${features_dir}/timing_context_scores.csv" \
    --assignment "native_timing_aware=${native_assignment}" \
    --assignment "normalized_architecture_on=${on_assignment}" \
    --assignment "normalized_architecture_off=${off_assignment}" \
    --output "${timing_out}"

  echo
  echo "== normalized path cuts =="
  python3 evaluation/evaluate_timing_path_cuts.py \
    --design "${design}" \
    --timing-report "${timing_report}" \
    --assignment "native_timing_aware=${native_assignment}" \
    --assignment "normalized_architecture_on=${on_assignment}" \
    --assignment "normalized_architecture_off=${off_assignment}" \
    --max-paths 100 \
    --output "${path_out}"

  echo
  echo "== normalized ON summary =="
  cat "${on_dir}/tritonpart_compatible_dynamic_guarded_repair_summary.csv"
  echo
  echo "== normalized OFF summary =="
  cat "${off_dir}/tritonpart_compatible_dynamic_guarded_repair_summary.csv"
  echo
  echo "== timing crossing =="
  cat "${timing_out}"
  echo
  echo "== path cuts =="
  cat "${path_out}"
done

echo
echo "== normalized smoke outputs =="
find results -path "*normalized_dynamic*smoke*.csv" -o -path "*tritonpart_compatible_normalized_dynamic*summary.csv" | sort
