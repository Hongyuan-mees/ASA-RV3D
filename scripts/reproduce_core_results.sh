#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
MODE="${1:-quick}"

DESIGNS="${DESIGNS:-riscv32i ibex picorv32 scr1_core_tuned}"
SCENARIOS="${SCENARIOS:-control_datapath_split memory_near_logic state_and_clock_protected}"
VERTICAL_DELAY_NS="${VERTICAL_DELAY_NS:-0.05}"
MAX_PATHS="${MAX_PATHS:-100}"

say() {
  printf '\n== %s ==\n' "$1"
}

run_present() {
  local path="$1"
  shift
  if [[ -f "$path" ]]; then
    "$@"
  else
    printf 'skip missing %s\n' "$path"
  fi
}

run_quick() {
  say "refresh result index"
  run_present scripts/generate_result_index.py \
    "$PYTHON_BIN" scripts/generate_result_index.py

  say "paper/readiness audit"
  run_present scripts/audit_paper_readiness.py \
    "$PYTHON_BIN" scripts/audit_paper_readiness.py

  say "key rollups"
  check_any "timing-regret main result" \
    results/benchmark_summary/timing_regret_guarded_four_core_summary.csv \
    results/benchmark_summary/timing_regret_guarded_all_scenarios_summary.csv \
    results/benchmark_summary/timing_regret_guarded_three_riscv_summary.csv

  check_any "pseudo-3D realization" \
    results/benchmark_summary/pseudo3d_realization_rollup.csv

  check_any "path-aware downstream" \
    results/benchmark_summary/path_aware_downstream_vertical_delay_rollup.csv

  check_any "component ablation" \
    results/benchmark_summary/component_ablation_rollup.csv

  check_any "architecture ablation" \
    results/benchmark_summary/architecture_ablation_rollup.csv

  check_any "scenario behavior" \
    results/benchmark_summary/scenario_behavior_rollup.csv

  check_any "result index" \
    results/benchmark_summary/result_index.csv
}

check_any() {
  local label="$1"
  shift
  local found=0

  for f in "$@"; do
    if [[ -f "$f" ]]; then
      printf 'ok %s: %s\n' "$label" "$f"
      found=1
      break
    fi
  done

  if [[ "$found" -eq 0 ]]; then
    printf 'missing %s; checked:' "$label"
    for f in "$@"; do
      printf ' %s' "$f"
    done
    printf '\n'
  fi
}

run_ablation() {
  say "component ablation"
  run_present run_component_ablation.py \
    "$PYTHON_BIN" run_component_ablation.py

  say "architecture ablation"
  run_present run_architecture_ablation.py \
    "$PYTHON_BIN" run_architecture_ablation.py
}

run_downstream() {
  say "path-aware downstream vertical-delay proxy"
  if [[ ! -f evaluation/evaluate_path_aware_downstream_vertical_delay.py ]]; then
    printf 'skip missing evaluation/evaluate_path_aware_downstream_vertical_delay.py\n'
    return
  fi

  for design in $DESIGNS; do
    for scenario in $SCENARIOS; do
      "$PYTHON_BIN" evaluation/evaluate_path_aware_downstream_vertical_delay.py \
        --design "$design" \
        --scenario "$scenario" \
        --max-paths "$MAX_PATHS" \
        --vertical-delay-ns "$VERTICAL_DELAY_NS"
    done
  done
}

run_robustness() {
  say "vertical-delay sweep"
  run_present run_path_aware_downstream_delay_sweep.py \
    "$PYTHON_BIN" run_path_aware_downstream_delay_sweep.py

  say "OpenSTA path-count sweep"
  run_present run_path_aware_downstream_pathcount_sweep.py \
    "$PYTHON_BIN" run_path_aware_downstream_pathcount_sweep.py
}

run_scenario() {
  say "scenario behavior analysis"
  run_present evaluation/analyze_scenario_behavior.py \
    "$PYTHON_BIN" evaluation/analyze_scenario_behavior.py

  run_present summarize_scenario_behavior.py \
    "$PYTHON_BIN" summarize_scenario_behavior.py
}

run_pseudo3d() {
  say "pseudo-3D realization proxy"
  run_present evaluation/evaluate_pseudo3d_realization.py \
    "$PYTHON_BIN" evaluation/evaluate_pseudo3d_realization.py

  run_present evaluation/export_pseudo3d_layout.py \
    "$PYTHON_BIN" evaluation/export_pseudo3d_layout.py
}

case "$MODE" in
  quick)
    run_quick
    ;;
  ablation)
    run_ablation
    run_quick
    ;;
  downstream)
    run_downstream
    run_quick
    ;;
  robustness)
    run_robustness
    run_quick
    ;;
  scenario)
    run_scenario
    run_quick
    ;;
  pseudo3d)
    run_pseudo3d
    run_quick
    ;;
  all)
    run_ablation
    run_downstream
    run_robustness
    run_scenario
    run_pseudo3d
    run_quick
    ;;
  *)
    cat <<'USAGE'
Usage: bash scripts/reproduce_core_results.sh [quick|ablation|downstream|robustness|scenario|pseudo3d|all]

Environment overrides:
  PYTHON_BIN=python3
  DESIGNS="riscv32i ibex picorv32 scr1_core_tuned"
  SCENARIOS="control_datapath_split memory_near_logic state_and_clock_protected"
  MAX_PATHS=100
  VERTICAL_DELAY_NS=0.05

The script refreshes repository-level reproducible analysis outputs from the
checked-in extracted features, timing reports, and partition assignments. It
does not rerun full OpenROAD-flow-scripts implementation.
USAGE
    exit 2
    ;;
esac

say "done"
