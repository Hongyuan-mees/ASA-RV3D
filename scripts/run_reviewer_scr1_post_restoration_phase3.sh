#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

scenario_filter="${1:-all}"
max_iterations="${2:-300}"
convergence_window="${3:-10}"
min_relative_gain="${4:-0.001}"

checkpoint_every="${CHECKPOINT_EVERY:-10}"
progress_every="${PROGRESS_EVERY_CANDIDATES:-1000}"
lambda_arch="${LAMBDA_ARCH:-1.0}"
lambda_physical="${LAMBDA_PHYSICAL:-1.0}"
lambda_timing="${LAMBDA_TIMING:-1.0}"
force="${FORCE:-0}"

design="scr1_core_tuned"
original_assignment="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
restored_assignment="results/${design}_baseline_feasibility_restoration/guarded/restored_assignment.csv"
features_dir="results/${design}_features"
timing_report="results/timing_reports/${design}_report_checks_max.rpt"
area_csv="results/benchmark_summary/${design}_openroad_instance_area.csv"
restoration_summary="results/benchmark_summary/${design}_feasibility_restoration_summary.csv"

scenarios=(control_datapath_split memory_near_logic state_and_clock_protected)

echo "== reviewer SCR1 post-restoration Phase-3 =="
echo "repo_root=${repo_root}"
echo "scenario_filter=${scenario_filter}"
echo "max_iterations=${max_iterations}"
echo "convergence_window=${convergence_window}"
echo "min_relative_gain=${min_relative_gain}"
echo "force=${force}"
echo "restored_assignment=${restored_assignment}"
echo "guard_reference_assignment=${original_assignment}"

python3 -m py_compile \
  partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py \
  partition/restore_baseline_feasibility.py

if [[ ! -s "${original_assignment}" ]]; then
  echo "missing original assignment: ${original_assignment}" >&2
  exit 2
fi
if [[ ! -s "${restored_assignment}" ]]; then
  echo "missing restored assignment: ${restored_assignment}" >&2
  echo "run first: bash scripts/run_reviewer_baseline_restoration.sh restore" >&2
  exit 2
fi
if [[ ! -s "${restoration_summary}" ]]; then
  echo "missing restoration summary: ${restoration_summary}" >&2
  exit 2
fi
if ! awk -F, 'NR>1 && $2=="guarded" && $3=="restored_guarded" && $12=="true" && $40=="pass" { found=1 } END { exit found ? 0 : 1 }' "${restoration_summary}"; then
  echo "guarded restoration has not passed the default area/cut/path guards; not running post-restoration Phase-3" >&2
  exit 3
fi
if [[ ! -d "${features_dir}" ]]; then
  echo "missing features directory: ${features_dir}" >&2
  exit 2
fi
if [[ ! -s "${timing_report}" ]]; then
  echo "missing timing report: ${timing_report}" >&2
  exit 2
fi
if [[ ! -s "${area_csv}" ]]; then
  echo "missing area csv: ${area_csv}" >&2
  exit 2
fi

run_one() {
  local scenario="$1"
  local mode="$2"
  local extra_flag=()
  local output_root="results/${design}_tritonpart_compatible_normalized_dynamic_reviewer_restored_baseline_guarded_repair"

  if [[ "${mode}" == "architecture_off" ]]; then
    extra_flag=(--architecture-off)
    output_root="results/${design}_tritonpart_compatible_normalized_dynamic_reviewer_restored_baseline_architecture_off_guarded_repair"
  fi

  local output_dir="${output_root}/${scenario}"
  local assignment="${output_dir}/tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
  local summary="${output_dir}/tritonpart_compatible_dynamic_guarded_repair_summary.csv"
  local manifest="${output_dir}/reviewer_restored_baseline_resume_manifest.json"

  echo
  echo "===== ${design} / ${scenario} / ${mode} / restored baseline ====="

  if [[ "${force}" == "1" && -d "${output_dir}" ]]; then
    echo "force=1, removing old output directory: ${output_dir}"
    rm -rf "${output_dir}"
  fi

  if [[ -s "${summary}" && -s "${assignment}" ]]; then
    echo "existing summary found, skip: ${summary}"
    return 0
  fi

  mkdir -p "${output_dir}"
  python3 - <<PY
import json
from pathlib import Path
manifest = {
    "design": "${design}",
    "scenario": "${scenario}",
    "architecture_mode": "${mode}",
    "original_initial_assignment": "${original_assignment}",
    "last_completed_iteration": 0,
    "latest_checkpoint": "${restored_assignment}",
    "trace_path": "${output_dir}/tritonpart_compatible_dynamic_guarded_repair_trace.csv",
    "objective": "0.000000",
    "cumulative_dynamic_gain": "0.000000",
    "checkpoint_every": ${checkpoint_every},
    "reviewer_note": "current tier state starts from guarded SCR1 baseline restoration; guards remain referenced to original native timing-aware assignment"
}
Path("${manifest}").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("${manifest}")
PY

  python3 -u partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py \
    "${extra_flag[@]}" \
    --resume-from "${manifest}" \
    --design "${design}" \
    --scenario "${scenario}" \
    --initial-assignment "${original_assignment}" \
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

for scenario in "${scenarios[@]}"; do
  if [[ "${scenario_filter}" != "all" && "${scenario_filter}" != "${scenario}" ]]; then
    continue
  fi
  run_one "${scenario}" architecture_on
  run_one "${scenario}" architecture_off
done

echo
echo "== reviewer SCR1 restored-baseline summaries =="
find results -path "*scr1_core_tuned_tritonpart_compatible_normalized_dynamic_reviewer_restored_baseline*summary.csv" | sort
