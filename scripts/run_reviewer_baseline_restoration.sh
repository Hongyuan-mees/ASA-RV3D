#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

phase="${1:-audit}"
state_file="results/benchmark_summary/reviewer_baseline_restoration_repo_state.txt"
mkdir -p results/benchmark_summary

if [[ "${phase}" != "audit" && "${phase}" != "restore" ]]; then
  echo "unsupported phase: ${phase}" >&2
  echo "supported phases: audit, restore" >&2
  exit 2
fi

{
  echo "== repo state =="
  echo "repo_root=."
  echo
  echo "-- git branch --"
  git branch --show-current || true
  echo
  echo "-- git status --"
  git status --short || true
  echo
  echo "-- git remotes --"
  git remote -v || true
  echo
  echo "-- experiment source head --"
  git rev-parse HEAD || true
  echo
  echo "-- recent commits --"
  git log -5 --oneline || true
} | tee "${state_file}"

echo
echo "== Python syntax check =="
python3 -m py_compile \
  scripts/audit_native_baseline_feasibility.py \
  partition/restore_baseline_feasibility.py

echo
echo "== Phase A: native baseline feasibility audit =="
python3 scripts/audit_native_baseline_feasibility.py

if [[ "${phase}" == "restore" ]]; then
  echo
  echo "== Phase B/C: SCR1 baseline feasibility restoration =="
  python3 partition/restore_baseline_feasibility.py \
    --design scr1_core_tuned \
    --initial-assignment results/scr1_core_tuned_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv \
    --features-dir results/scr1_core_tuned_features \
    --instance-area results/benchmark_summary/scr1_core_tuned_openroad_instance_area.csv \
    --timing-report results/timing_reports/scr1_core_tuned_report_checks_max.rpt \
    --policy area_only \
    --policy guarded \
    --max-paths 100 \
    --max-cut-regret 0.05 \
    --max-pavg-regret 0.0 \
    --max-pwst-delta 0.0 \
    --output-root results/scr1_core_tuned_baseline_feasibility_restoration \
    --summary-output results/benchmark_summary/scr1_core_tuned_feasibility_restoration_summary.csv \
    --moves-output results/benchmark_summary/scr1_core_tuned_feasibility_restoration_moves.csv
fi

echo
echo "== outputs =="
echo "${state_file}"
echo "results/benchmark_summary/native_baseline_feasibility_audit.csv"
echo "results/benchmark_summary/scr1_baseline_infeasibility_analysis.md"
if [[ "${phase}" == "restore" ]]; then
  echo "results/benchmark_summary/scr1_core_tuned_feasibility_restoration_summary.csv"
  echo "results/benchmark_summary/scr1_core_tuned_feasibility_restoration_moves.csv"
  echo "results/scr1_core_tuned_baseline_feasibility_restoration/area_only/restored_assignment.csv"
  echo "results/scr1_core_tuned_baseline_feasibility_restoration/guarded/restored_assignment.csv"
fi
