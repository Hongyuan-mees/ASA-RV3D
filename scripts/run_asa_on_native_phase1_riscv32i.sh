#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(pwd)"
ORFS_FLOW="${ORFS_FLOW:-$HOME/openroad-flow-scripts/flow}"
DESIGN="riscv32i"
SCENARIO="state_and_clock_protected"
PHASE_DIR="$ORFS_FLOW/rv3d_asa_on_native_phase1/$DESIGN"

mkdir -p "$PHASE_DIR"

echo "== ASA-on-native repair =="
python3 scripts/run_timing_aware_start_experiments.py \
  --design "$DESIGN" \
  --scenario "$SCENARIO"

NATIVE_ASSIGNMENT="results/${DESIGN}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"
ASA_ASSIGNMENT="results/${DESIGN}_timing_aware_start_asa/${SCENARIO}/tritonpart_timing_regret_guarded_repair_assignment.csv"
TIMING_REPORT="results/timing_reports/${DESIGN}_report_checks_max.rpt"

echo
echo "== timing path cut metrics =="
python3 evaluation/evaluate_timing_path_cuts.py \
  --design "$DESIGN" \
  --timing-report "$TIMING_REPORT" \
  --assignment "native_timing_aware=$NATIVE_ASSIGNMENT" \
  --assignment "asa_on_native=$ASA_ASSIGNMENT" \
  --max-paths 100 \
  --output "results/benchmark_summary/asa_on_native_${DESIGN}_path_cuts.csv"

echo
echo "== prepare area-balance inputs for OpenROAD =="
cp scripts/extract_openroad_assignment_area_balance.tcl "$PHASE_DIR/extract_area_balance.tcl"
cp "$NATIVE_ASSIGNMENT" "$PHASE_DIR/native_timing_aware_assignment.csv"
cp "$ASA_ASSIGNMENT" "$PHASE_DIR/asa_on_native_assignment.csv"

cat > "$PHASE_DIR/native_area.tcl" <<'TCL'
set ::env(DESIGN) "riscv32i"
set ::env(CASE) "native_timing_aware"
set ::env(ODB_FILE) "/work/results/sky130hd/riscv32i/base/6_final.odb"
set ::env(ASSIGNMENT_FILE) "/work/rv3d_asa_on_native_phase1/riscv32i/native_timing_aware_assignment.csv"
set ::env(OUTPUT_CSV) "/work/rv3d_asa_on_native_phase1/riscv32i/native_timing_aware_area_balance.csv"
source "/work/rv3d_asa_on_native_phase1/riscv32i/extract_area_balance.tcl"
TCL

cat > "$PHASE_DIR/asa_area.tcl" <<'TCL'
set ::env(DESIGN) "riscv32i"
set ::env(CASE) "asa_on_native"
set ::env(ODB_FILE) "/work/results/sky130hd/riscv32i/base/6_final.odb"
set ::env(ASSIGNMENT_FILE) "/work/rv3d_asa_on_native_phase1/riscv32i/asa_on_native_assignment.csv"
set ::env(OUTPUT_CSV) "/work/rv3d_asa_on_native_phase1/riscv32i/asa_on_native_area_balance.csv"
source "/work/rv3d_asa_on_native_phase1/riscv32i/extract_area_balance.tcl"
TCL

echo
echo "== native area balance =="
(
  cd "$ORFS_FLOW"
  ./util/docker_shell openroad /work/rv3d_asa_on_native_phase1/riscv32i/native_area.tcl
)

echo
echo "== ASA-on-native area balance =="
(
  cd "$ORFS_FLOW"
  ./util/docker_shell openroad /work/rv3d_asa_on_native_phase1/riscv32i/asa_area.tcl
)

mkdir -p "$REPO_ROOT/results/benchmark_summary"
cp "$PHASE_DIR/native_timing_aware_area_balance.csv" \
  "$REPO_ROOT/results/benchmark_summary/asa_on_native_${DESIGN}_native_area_balance.csv"
cp "$PHASE_DIR/asa_on_native_area_balance.csv" \
  "$REPO_ROOT/results/benchmark_summary/asa_on_native_${DESIGN}_asa_area_balance.csv"

echo
echo "== phase-1 summary =="
python3 scripts/summarize_asa_on_native_phase1.py \
  --design "$DESIGN" \
  --scenario "$SCENARIO"

echo
echo "== outputs =="
echo "results/benchmark_summary/asa_on_native_${DESIGN}_path_cuts.csv"
echo "results/benchmark_summary/asa_on_native_${DESIGN}_native_area_balance.csv"
echo "results/benchmark_summary/asa_on_native_${DESIGN}_asa_area_balance.csv"
echo "results/benchmark_summary/asa_on_native_${DESIGN}_summary.csv"
echo "results/benchmark_summary/asa_on_native_${DESIGN}_analysis.md"
echo "results/benchmark_summary/timing_aware_start_asa_summary.csv"
