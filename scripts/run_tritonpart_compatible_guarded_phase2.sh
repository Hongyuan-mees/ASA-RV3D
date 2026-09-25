#!/usr/bin/env bash
set -euo pipefail

design="${1:-picorv32}"
scenario="${2:-state_and_clock_protected}"
repo_dir="$(pwd)"
flow_dir="${ORFS_FLOW_DIR:-$HOME/openroad-flow-scripts/flow}"
work_dir="${flow_dir}/rv3d_tritonpart_compatible_guarded_phase2/${design}"
odb_file="${flow_dir}/results/sky130hd/${design}/base/6_final.odb"

native_assignment="results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
trace="results/${design}_timing_aware_start_asa/${scenario}/local_refinement_trace.csv"
features_dir="results/${design}_features"
timing_report="results/timing_reports/${design}_report_checks_max.rpt"
output_dir="results/${design}_tritonpart_compatible_guarded_repair/${scenario}"
area_csv="results/benchmark_summary/${design}_openroad_instance_area.csv"

echo "== TritonPart-compatible ASA guarded Phase 2 =="
echo "design=${design}"
echo "scenario=${scenario}"

if [[ ! -f "${odb_file}" ]]; then
  echo "missing ODB: ${odb_file}" >&2
  exit 2
fi

mkdir -p "${work_dir}" "results/benchmark_summary"
cp "${repo_dir}/scripts/extract_openroad_instance_area.tcl" "${work_dir}/"
rm -f "${work_dir}/instance_area.csv" "${repo_dir}/${area_csv}"
rm -rf "${output_dir}"

(
  cd "${flow_dir}"
  ./util/docker_shell bash -lc \
    "cd /work && DESIGN='${design}' ODB_FILE='/work/results/sky130hd/${design}/base/6_final.odb' OUTPUT_CSV='/work/rv3d_tritonpart_compatible_guarded_phase2/${design}/instance_area.csv' openroad /work/rv3d_tritonpart_compatible_guarded_phase2/${design}/scripts/extract_openroad_instance_area.tcl"
)

cp "${work_dir}/instance_area.csv" "${repo_dir}/${area_csv}"

python3 partition/partition_tritonpart_compatible_guarded_repair.py \
  --design "${design}" \
  --scenario "${scenario}" \
  --initial-assignment "${native_assignment}" \
  --trace "${trace}" \
  --features-dir "${features_dir}" \
  --instance-area "${area_csv}" \
  --timing-report "${timing_report}" \
  --max-paths 100 \
  --max-cut-regret 0.05 \
  --max-pavg-regret 0.0 \
  --max-pwst-delta 0.0 \
  --output-dir "${output_dir}"

assignment="${output_dir}/tritonpart_compatible_guarded_repair_assignment.csv"

python3 evaluation/evaluate_timing_crossing.py \
  --design "${design}" \
  --features-dir "${features_dir}" \
  --timing "${features_dir}/timing_context_scores.csv" \
  --assignment "native_timing_aware=${native_assignment}" \
  --assignment "tritonpart_compatible_asa=${assignment}" \
  --output "results/benchmark_summary/${design}_${scenario}_tritonpart_compatible_guarded_timing_crossing.csv"

python3 evaluation/evaluate_timing_path_cuts.py \
  --design "${design}" \
  --timing-report "${timing_report}" \
  --assignment "native_timing_aware=${native_assignment}" \
  --assignment "tritonpart_compatible_asa=${assignment}" \
  --max-paths 100 \
  --output "results/benchmark_summary/${design}_${scenario}_tritonpart_compatible_guarded_path_cuts.csv"

echo
echo "== guarded repair summary =="
cat "${output_dir}/tritonpart_compatible_guarded_repair_summary.csv"
echo
echo "== timing crossing =="
cat "results/benchmark_summary/${design}_${scenario}_tritonpart_compatible_guarded_timing_crossing.csv"
echo
echo "== path cuts =="
cat "results/benchmark_summary/${design}_${scenario}_tritonpart_compatible_guarded_path_cuts.csv"
