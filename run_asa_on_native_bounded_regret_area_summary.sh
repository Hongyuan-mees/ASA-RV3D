#!/usr/bin/env bash
set -euo pipefail

design="${1:-picorv32}"
scenario="${2:-state_and_clock_protected}"
repo_dir="$(pwd)"
flow_dir="${ORFS_FLOW_DIR:-$HOME/openroad-flow-scripts/flow}"
work_dir="${flow_dir}/rv3d_asa_on_native_phase1/${design}"
odb_file="${flow_dir}/results/sky130hd/${design}/base/6_final.odb"

mkdir -p "${work_dir}" "${repo_dir}/results/benchmark_summary"

cp "${repo_dir}/extract_openroad_assignment_area_balance.tcl" "${work_dir}/"
cp "${repo_dir}/results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv" \
  "${work_dir}/native_timing_aware_assignment.csv"

for budget in 0p05 0p10 0p20; do
  cp "${repo_dir}/results/${design}_asa_on_native_cut_regret_replay/${scenario}/cut_regret_${budget}_assignment.csv" \
    "${work_dir}/cut_regret_${budget}_assignment.csv"
done

run_area() {
  local case_name="$1"
  local assignment_name="$2"
  local output_name="$3"

  (
    cd "${flow_dir}"
    ./util/docker_shell bash -lc \
      "cd /work && DESIGN='${design}' CASE='${case_name}' ODB_FILE='/work/results/sky130hd/${design}/base/6_final.odb' ASSIGNMENT_FILE='/work/rv3d_asa_on_native_phase1/${design}/${assignment_name}' OUTPUT_CSV='/work/rv3d_asa_on_native_phase1/${design}/${output_name}' openroad /work/rv3d_asa_on_native_phase1/${design}/extract_openroad_assignment_area_balance.tcl"
  )
}

if [[ ! -f "${odb_file}" ]]; then
  echo "missing ODB: ${odb_file}" >&2
  exit 2
fi

run_area "native_timing_aware" "native_timing_aware_assignment.csv" "native_timing_aware_area_balance.csv"
run_area "cut_regret_0p05" "cut_regret_0p05_assignment.csv" "cut_regret_0p05_area_balance.csv"
run_area "cut_regret_0p10" "cut_regret_0p10_assignment.csv" "cut_regret_0p10_area_balance.csv"
run_area "cut_regret_0p20" "cut_regret_0p20_assignment.csv" "cut_regret_0p20_area_balance.csv"

cp "${work_dir}/native_timing_aware_area_balance.csv" \
  "${repo_dir}/results/benchmark_summary/asa_on_native_${design}_native_area_balance.csv"
cp "${work_dir}/cut_regret_0p05_area_balance.csv" \
  "${repo_dir}/results/benchmark_summary/asa_on_native_${design}_cut_regret_0p05_area_balance.csv"
cp "${work_dir}/cut_regret_0p10_area_balance.csv" \
  "${repo_dir}/results/benchmark_summary/asa_on_native_${design}_cut_regret_0p10_area_balance.csv"
cp "${work_dir}/cut_regret_0p20_area_balance.csv" \
  "${repo_dir}/results/benchmark_summary/asa_on_native_${design}_cut_regret_0p20_area_balance.csv"

python3 summarize_asa_on_native_bounded_regret.py \
  --design "${design}" \
  --scenario "${scenario}" \
  --eval "results/benchmark_summary/asa_on_native_${design}_${scenario}_cut_regret_replay_eval.csv" \
  --output-summary "results/benchmark_summary/asa_on_native_${design}_${scenario}_bounded_regret_summary.csv" \
  --output-analysis "results/benchmark_summary/asa_on_native_${design}_${scenario}_bounded_regret_analysis.md"

echo
echo "== bounded-regret summary =="
cat "results/benchmark_summary/asa_on_native_${design}_${scenario}_bounded_regret_summary.csv"
echo
cat "results/benchmark_summary/asa_on_native_${design}_${scenario}_bounded_regret_analysis.md"

