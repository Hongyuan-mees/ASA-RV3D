#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

design_filter="${1:-all}"
scenario_filter="${2:-all}"
max_iterations="${3:-300}"
convergence_window="${4:-10}"
min_relative_gain="${5:-0.001}"

lambda_arch="${LAMBDA_ARCH:-1.0}"
lambda_physical="${LAMBDA_PHYSICAL:-1.0}"
lambda_timing="${LAMBDA_TIMING:-1.0}"
checkpoint_every="${CHECKPOINT_EVERY:-10}"
progress_every="${PROGRESS_EVERY_CANDIDATES:-1000}"

cases=(
  "picorv32 control_datapath_split"
  "picorv32 memory_near_logic"
  "picorv32 state_and_clock_protected"
  "riscv32i control_datapath_split"
  "riscv32i memory_near_logic"
  "riscv32i state_and_clock_protected"
  "scr1_core_tuned control_datapath_split"
  "scr1_core_tuned memory_near_logic"
  "scr1_core_tuned state_and_clock_protected"
)

echo "== normalized dynamic convergence Phase-3 =="
echo "repo_root=${repo_root}"
echo "design_filter=${design_filter}"
echo "scenario_filter=${scenario_filter}"
echo "max_iterations=${max_iterations}"
echo "convergence_window=${convergence_window}"
echo "min_relative_gain=${min_relative_gain}"
echo "lambda_arch=${lambda_arch}"
echo "lambda_physical=${lambda_physical}"
echo "lambda_timing=${lambda_timing}"
echo "checkpoint_every=${checkpoint_every}"

run_one() {
  local design="$1"
  local scenario="$2"
  local mode="$3"
  local extra_flag=()

  if [[ "${mode}" == "architecture_off" ]]; then
    extra_flag=(--architecture-off)
  fi

  local native_assignment="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
  local features_dir="results/${design}_features"
  local timing_report="results/timing_reports/${design}_report_checks_max.rpt"
  local area_csv="results/benchmark_summary/${design}_openroad_instance_area.csv"
  local output_root="results/${design}_tritonpart_compatible_normalized_dynamic_convergence_guarded_repair"

  if [[ "${mode}" == "architecture_off" ]]; then
    output_root="results/${design}_tritonpart_compatible_normalized_dynamic_convergence_architecture_off_guarded_repair"
  fi

  local output_dir="${output_root}/${scenario}"
  local assignment="${output_dir}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  local summary="${output_dir}/tritonpart_compatible_dynamic_guarded_repair_summary.csv"
  local manifest="${output_dir}/resume_manifest.json"
  local resume_flag=()

  echo
  echo "===== ${design} / ${scenario} / ${mode} ====="

  if [[ ! -s "${native_assignment}" ]]; then
    echo "missing native assignment: ${native_assignment}" >&2
    return 2
  fi
  if [[ ! -d "${features_dir}" ]]; then
    echo "missing features directory: ${features_dir}" >&2
    return 2
  fi
  if [[ ! -s "${timing_report}" ]]; then
    echo "missing timing report: ${timing_report}" >&2
    return 2
  fi
  if [[ ! -s "${area_csv}" ]]; then
    echo "missing area csv: ${area_csv}" >&2
    return 2
  fi

  if [[ -s "${summary}" && -s "${assignment}" ]]; then
    echo "existing summary found, skip: ${summary}"
    return 0
  fi
  if [[ -s "${manifest}" ]]; then
    echo "resume from: ${manifest}"
    resume_flag=(--resume-from "${manifest}")
  else
    echo "start from native assignment"
  fi

  python3 -u partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py \
    "${extra_flag[@]}" \
    "${resume_flag[@]}" \
    --design "${design}" \
    --scenario "${scenario}" \
    --initial-assignment "${native_assignment}" \
    --features-dir "${features_dir}" \
    --instance-area "${area_csv}" \
    --timing-report "${timing_report}" \
    --max-paths 100 \
    --max-iterations "${max_iterations}" \
    --max-cut-regret 0.05 \
    --max-pavg-regret 0.0 \
    --max-pwst-delta 0.0 \
    --lambda-arch "${lambda_arch}" \
    --lambda-physical "${lambda_physical}" \
    --lambda-timing "${lambda_timing}" \
    --checkpoint-every "${checkpoint_every}" \
    --convergence-window "${convergence_window}" \
    --min-relative-gain "${min_relative_gain}" \
    --progress-every-candidates "${progress_every}" \
    --output-dir "${output_dir}"
}

python3 -m py_compile \
  partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py \
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

  run_one "${design}" "${scenario}" architecture_on
  run_one "${design}" "${scenario}" architecture_off
done

echo
echo "== convergence Phase-3 summaries =="
find results -path "*tritonpart_compatible_normalized_dynamic_convergence*summary.csv" | sort
