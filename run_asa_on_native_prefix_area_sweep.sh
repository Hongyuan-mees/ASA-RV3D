#!/usr/bin/env bash
set -euo pipefail

design="${1:-picorv32}"
scenario="${2:-state_and_clock_protected}"
repo_dir="$(pwd)"
flow_dir="${ORFS_FLOW_DIR:-$HOME/openroad-flow-scripts/flow}"
work_dir="${flow_dir}/rv3d_asa_on_native_prefix_sweep/${design}/${scenario}"
odb_file="${flow_dir}/results/sky130hd/${design}/base/6_final.odb"

prefixes=(5 10 15 20 23 25 26 27)

mkdir -p "${work_dir}" "${repo_dir}/results/benchmark_summary"

python3 export_asa_on_native_prefix_sweep.py \
  --design "${design}" \
  --scenario "${scenario}" \
  --initial-assignment "results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv" \
  --trace "results/${design}_timing_aware_start_asa/${scenario}/local_refinement_trace.csv" \
  --output-dir "results/${design}_asa_on_native_prefix_sweep/${scenario}" \
  --output-summary "results/benchmark_summary/asa_on_native_${design}_${scenario}_prefix_sweep.csv"

cp "${repo_dir}/extract_openroad_assignment_area_balance.tcl" "${work_dir}/"
for prefix in "${prefixes[@]}"; do
  cp "${repo_dir}/results/${design}_asa_on_native_prefix_sweep/${scenario}/prefix_$(printf '%03d' "${prefix}")_assignment.csv" \
    "${work_dir}/prefix_$(printf '%03d' "${prefix}")_assignment.csv"
done

if [[ ! -f "${odb_file}" ]]; then
  echo "missing ODB: ${odb_file}" >&2
  exit 2
fi

for prefix in "${prefixes[@]}"; do
  label="prefix_$(printf '%03d' "${prefix}")"
  (
    cd "${flow_dir}"
    ./util/docker_shell bash -lc \
      "cd /work && DESIGN='${design}' CASE='${label}' ODB_FILE='/work/results/sky130hd/${design}/base/6_final.odb' ASSIGNMENT_FILE='/work/rv3d_asa_on_native_prefix_sweep/${design}/${scenario}/${label}_assignment.csv' OUTPUT_CSV='/work/rv3d_asa_on_native_prefix_sweep/${design}/${scenario}/${label}_area_balance.csv' openroad /work/rv3d_asa_on_native_prefix_sweep/${design}/${scenario}/extract_openroad_assignment_area_balance.tcl"
  )
  cp "${work_dir}/${label}_area_balance.csv" \
    "${repo_dir}/results/benchmark_summary/asa_on_native_${design}_${scenario}_${label}_area_balance.csv"
done

DESIGN="${design}" SCENARIO="${scenario}" python3 - <<'PY'
import csv
import os
from pathlib import Path

design = os.environ["DESIGN"]
scenario = os.environ["SCENARIO"]
summary = Path(f"results/benchmark_summary/asa_on_native_{design}_{scenario}_prefix_sweep.csv")
rows = list(csv.DictReader(summary.open(newline="", encoding="utf-8")))
out = []
for row in rows:
    prefix = int(row["prefix"])
    area_path = Path(f"results/benchmark_summary/asa_on_native_{design}_{scenario}_prefix_{prefix:03d}_area_balance.csv")
    area = list(csv.DictReader(area_path.open(newline="", encoding="utf-8")))[0]
    merged = dict(row)
    merged.update({
        "area_balance_pass": area["balance_constraint_2_pass"],
        "area_weight_balance": area["area_weight_balance"],
        "tier0_area_fraction": area["tier0_area_fraction"],
        "tier1_area_fraction": area["tier1_area_fraction"],
    })
    out.append(merged)

path = Path(f"results/benchmark_summary/asa_on_native_{design}_{scenario}_prefix_area_sweep.csv")
with path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    writer.writeheader()
    writer.writerows(out)
print(path)
PY

cat "results/benchmark_summary/asa_on_native_${design}_${scenario}_prefix_area_sweep.csv"
