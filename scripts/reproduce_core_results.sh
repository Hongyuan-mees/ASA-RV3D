#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ORFS_FLOW_DIR="${ORFS_FLOW_DIR:-$HOME/openroad-flow-scripts/flow}"
DESIGNS="${DESIGNS:-ibex riscv32i picorv32}"
SCENARIOS="${SCENARIOS:-control_datapath_split memory_near_logic state_and_clock_protected}"

msg() {
  printf '\n=== %s ===\n' "$*"
}

need_file() {
  if [ ! -f "$1" ]; then
    echo "Missing required file: $1" >&2
    return 1
  fi
}

check_orfs_artifacts() {
  local design="$1"
  local base="$ORFS_FLOW_DIR/results/sky130hd/$design/base"
  need_file "$base/6_final.v"
  need_file "$base/6_final.def"
  need_file "$base/6_final.odb"
  need_file "$base/6_final.sdc"
  need_file "$base/6_final.spef"
}

extract_core_features() {
  local design="$1"

  python3 scripts/extract_orfs_baseline.py \
    --design "$design" \
    --platform sky130hd \
    --orfs-flow-dir "$ORFS_FLOW_DIR" \
    --output-dir "results/${design}_features"

  python3 classifier/architecture_classifier.py \
    --features-dir "results/${design}_features"

  python3 evaluation/graph_context_score.py \
    --features-dir "results/${design}_features"

  python3 classifier/architecture_mapper.py \
    --features-dir "results/${design}_features"

  python3 evaluation/extract_physical_features.py \
    --design "$design" \
    --features-dir "results/${design}_features" \
    --orfs-flow-dir "$ORFS_FLOW_DIR"

  python3 evaluation/diagnose_def_matching.py \
    --design "$design" \
    --features-dir "results/${design}_features" \
    --orfs-flow-dir "$ORFS_FLOW_DIR"
}

refresh_physical_scores() {
  python3 evaluation/summarize_physical_coverage.py

  for design in $DESIGNS; do
    python3 evaluation/physical_context_score.py \
      --design "$design" \
      --features-dir "results/${design}_features" \
      --coverage-summary results/benchmark_summary/physical_coverage_summary.csv
  done
}

emit_timing_reports() {
  local design="$1"
  local work_dir="$ORFS_FLOW_DIR/rv3d_timing_reports"
  mkdir -p "$work_dir"

  cat > "$work_dir/${design}_report_checks_clean.tcl" <<EOF
read_liberty /OpenROAD-flow-scripts/flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
read_db /work/results/sky130hd/$design/base/6_final.odb
read_sdc /work/results/sky130hd/$design/base/6_final.sdc
read_spef /work/results/sky130hd/$design/base/6_final.spef

report_tns > /work/rv3d_timing_reports/${design}_tns.rpt
report_wns > /work/rv3d_timing_reports/${design}_wns.rpt
report_checks -path_delay max -fields {slew cap input_pins fanout} -digits 4 -group_path_count 50 > /work/rv3d_timing_reports/${design}_report_checks_max.rpt
report_checks -path_delay min -fields {slew cap input_pins fanout} -digits 4 -group_path_count 50 > /work/rv3d_timing_reports/${design}_report_checks_min.rpt

exit
EOF

  (cd "$ORFS_FLOW_DIR" && util/docker_shell "cd /work && openroad rv3d_timing_reports/${design}_report_checks_clean.tcl")

  mkdir -p results/timing_reports
  cp "$work_dir/${design}_report_checks_max.rpt" results/timing_reports/
  cp "$work_dir/${design}_report_checks_min.rpt" results/timing_reports/
  cp "$work_dir/${design}_tns.rpt" results/timing_reports/
  cp "$work_dir/${design}_wns.rpt" results/timing_reports/
}

extract_timing_context() {
  local design="$1"
  python3 evaluation/extract_timing_context.py \
    --design "$design" \
    --features-dir "results/${design}_features"
}

run_tritonpart() {
  local design="$1"
  local local_dir="$ORFS_FLOW_DIR/rv3d_tritonpart_${design}"

  python3 evaluation/export_tritonpart_hgr.py --design "$design"

  mkdir -p "$local_dir"
  cp "results/${design}_tritonpart_baseline/${design}.hgr" "$local_dir/${design}.hgr"
  cp "results/${design}_tritonpart_baseline/run_tritonpart.tcl" "$local_dir/run_tritonpart.tcl"

  python3 - <<PY
from pathlib import Path
design = "$design"
p = Path("$local_dir/run_tritonpart.tcl")
s = p.read_text()
s = s.replace(f"/work/rv3d_tritonpart/{design}.hgr", f"/work/rv3d_tritonpart_{design}/{design}.hgr")
p.write_text(s)
PY

  (cd "$ORFS_FLOW_DIR" && util/docker_shell "cd /work/rv3d_tritonpart_${design} && openroad run_tritonpart.tcl")

  cp "$local_dir/${design}.hgr.part.2" "results/${design}_tritonpart_baseline/"
  python3 evaluation/import_tritonpart_partition.py --design "$design"
}

run_repairs() {
  local design="$1"
  local scenario="$2"

  python3 partition/partition_tritonpart_guarded_repair.py \
    --design "$design" \
    --scenario "$scenario" \
    --output-dir "results/${design}_tritonpart_guarded_repair/${scenario}"

  python3 partition/partition_tritonpart_timing_regret_guarded_repair.py \
    --design "$design" \
    --scenario "$scenario" \
    --output-dir "results/${design}_tritonpart_timing_regret_guarded_repair/${scenario}"

  python3 evaluation/evaluate_timing_crossing.py \
    --design "$design" \
    --features-dir "results/${design}_features" \
    --timing "results/${design}_features/timing_context_scores.csv" \
    --assignment "tritonpart=results/${design}_tritonpart_baseline/tritonpart_assignment.csv" \
    --assignment "guarded=results/${design}_tritonpart_guarded_repair/${scenario}/tritonpart_guarded_repair_assignment.csv" \
    --assignment "timing_regret_guarded=results/${design}_tritonpart_timing_regret_guarded_repair/${scenario}/tritonpart_timing_regret_guarded_repair_assignment.csv" \
    --output "results/benchmark_summary/timing_regret_crossing/${design}_${scenario}_timing_crossing.csv"
}

write_three_design_summary() {
  python3 - <<'PY'
import csv
from pathlib import Path

designs = ["riscv32i", "ibex", "picorv32"]
scenarios = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]

rows = []
for design in designs:
    for scenario in scenarios:
        path = Path(f"results/benchmark_summary/timing_regret_crossing/{design}_{scenario}_timing_crossing.csv")
        data = {row["case"]: row for row in csv.DictReader(path.open(newline="", encoding="utf-8"))}
        tri = data["tritonpart"]
        guarded = data["guarded"]
        timed = data["timing_regret_guarded"]

        tri_tw = float(tri["timing_weighted_crossing"])
        guarded_tw = float(guarded["timing_weighted_crossing"])
        timed_tw = float(timed["timing_weighted_crossing"])

        rows.append({
            "design": design,
            "scenario": scenario,
            "tritonpart_timing_weighted_crossing": tri["timing_weighted_crossing"],
            "guarded_timing_weighted_crossing": guarded["timing_weighted_crossing"],
            "timing_regret_guarded_timing_weighted_crossing": timed["timing_weighted_crossing"],
            "reduction_vs_guarded": f"{(guarded_tw - timed_tw) / guarded_tw:.6f}",
            "reduction_vs_tritonpart": f"{(tri_tw - timed_tw) / tri_tw:.6f}",
            "guarded_crossing_nets": guarded["crossing_nets"],
            "timing_regret_guarded_crossing_nets": timed["crossing_nets"],
            "guarded_high_timing_crossing_nets": guarded["high_timing_crossing_nets"],
            "timing_regret_guarded_high_timing_crossing_nets": timed["high_timing_crossing_nets"],
        })

out = Path("results/benchmark_summary/timing_regret_guarded_three_riscv_summary.csv")
out.parent.mkdir(parents=True, exist_ok=True)
fields = [
    "design", "scenario",
    "tritonpart_timing_weighted_crossing",
    "guarded_timing_weighted_crossing",
    "timing_regret_guarded_timing_weighted_crossing",
    "reduction_vs_guarded",
    "reduction_vs_tritonpart",
    "guarded_crossing_nets",
    "timing_regret_guarded_crossing_nets",
    "guarded_high_timing_crossing_nets",
    "timing_regret_guarded_high_timing_crossing_nets",
]
with out.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(out)
PY
}

main() {
  msg "Checking ORFS final artifacts"
  for design in $DESIGNS; do
    check_orfs_artifacts "$design"
  done

  msg "Extracting features and context"
  for design in $DESIGNS; do
    msg "Features: $design"
    extract_core_features "$design"
  done

  msg "Refreshing physical context scores"
  refresh_physical_scores

  msg "Generating OpenSTA timing context"
  for design in $DESIGNS; do
    msg "Timing: $design"
    emit_timing_reports "$design"
    extract_timing_context "$design"
  done

  msg "Running TritonPart"
  for design in $DESIGNS; do
    msg "TritonPart: $design"
    run_tritonpart "$design"
  done

  msg "Running guarded and timing-regret repairs"
  for design in $DESIGNS; do
    for scenario in $SCENARIOS; do
      msg "Repair: $design $scenario"
      run_repairs "$design" "$scenario"
    done
  done

  msg "Writing summaries and final figures"
  write_three_design_summary
  python3 evaluation/plot_final_timing_results.py

  msg "Done"
  cat results/benchmark_summary/timing_regret_guarded_three_riscv_summary.csv
}

main "$@"
