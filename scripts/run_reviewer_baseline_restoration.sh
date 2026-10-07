#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

phase="${1:-audit}"
state_file="results/benchmark_summary/reviewer_baseline_restoration_repo_state.txt"
mkdir -p results/benchmark_summary

if [[ "${phase}" != "audit" ]]; then
  echo "unsupported phase: ${phase}" >&2
  echo "supported phases: audit" >&2
  exit 2
fi

{
  echo "== repo state =="
  echo "repo_root=${repo_root}"
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
  echo "-- git head --"
  git rev-parse HEAD || true
  echo
  echo "-- recent commits --"
  git log -5 --oneline || true
} | tee "${state_file}"

echo
echo "== Phase A: native baseline feasibility audit =="
python3 scripts/audit_native_baseline_feasibility.py

echo
echo "== outputs =="
echo "${state_file}"
echo "results/benchmark_summary/native_baseline_feasibility_audit.csv"
echo "results/benchmark_summary/scr1_baseline_infeasibility_analysis.md"
