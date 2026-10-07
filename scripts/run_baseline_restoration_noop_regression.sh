#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

design_filter="${1:-all}"
designs=(picorv32 riscv32i)

echo "== reviewer baseline restoration no-op regression =="
echo "repo_root=${repo_root}"
echo "design_filter=${design_filter}"

python3 -m py_compile \
  partition/restore_baseline_feasibility.py \
  scripts/summarize_baseline_restoration_noop.py

for design in "${designs[@]}"; do
  if [[ "${design_filter}" != "all" && "${design_filter}" != "${design}" ]]; then
    continue
  fi

  echo
  echo "===== ${design} no-op restoration ====="
  python3 partition/restore_baseline_feasibility.py \
    --design "${design}" \
    --initial-assignment "results/${design}_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv" \
    --features-dir "results/${design}_features" \
    --instance-area "results/benchmark_summary/${design}_openroad_instance_area.csv" \
    --timing-report "results/timing_reports/${design}_report_checks_max.rpt" \
    --policy guarded \
    --max-paths 100 \
    --max-cut-regret 0.05 \
    --max-pavg-regret 0.0 \
    --max-pwst-delta 0.0 \
    --output-root "results/${design}_baseline_feasibility_restoration_noop" \
    --summary-output "results/benchmark_summary/${design}_baseline_restoration_noop_summary.csv" \
    --moves-output "results/benchmark_summary/${design}_baseline_restoration_noop_moves.csv"
done

echo
echo "== no-op summary =="
python3 scripts/summarize_baseline_restoration_noop.py

echo
echo "== outputs =="
echo "results/benchmark_summary/baseline_restoration_noop_check.csv"
for design in "${designs[@]}"; do
  if [[ "${design_filter}" != "all" && "${design_filter}" != "${design}" ]]; then
    continue
  fi
  echo "results/benchmark_summary/${design}_baseline_restoration_noop_summary.csv"
  echo "results/benchmark_summary/${design}_baseline_restoration_noop_moves.csv"
  echo "results/${design}_baseline_feasibility_restoration_noop/guarded/restored_assignment.csv"
done
