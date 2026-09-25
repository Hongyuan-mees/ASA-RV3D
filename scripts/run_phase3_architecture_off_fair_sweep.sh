#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$HOME/RV3D_Public}"
iterations="${2:-200}"
cd "$repo_root"

designs=(picorv32 riscv32i)
scenarios=(control_datapath_split memory_near_logic state_and_clock_protected)

echo "== Phase-3 architecture-OFF fair sweep =="
echo "repo_root=${repo_root}"
echo "iterations=${iterations}"

for design in "${designs[@]}"; do
  for scenario in "${scenarios[@]}"; do
    echo
    echo "===== architecture OFF fair run: ${design} / ${scenario} / ${iterations} iterations ====="
    bash scripts/run_dynamic_architecture_off_phase3.sh "$design" "$scenario" "$iterations"
  done
done

echo
echo "== refresh dynamic architecture ablation summary =="
python3 scripts/summarize_dynamic_architecture_ablation_phase3.py
cat results/benchmark_summary/dynamic_architecture_ablation_phase3_rollup.csv

echo
echo "== refresh architecture structural summary =="
python3 evaluation/evaluate_architecture_structural_crossing.py \
  --scenario control_datapath_split \
  --scenario memory_near_logic \
  --scenario state_and_clock_protected
cat results/benchmark_summary/dynamic_architecture_structural_phase3_rollup.csv

echo
echo "== git status =="
git status --short
