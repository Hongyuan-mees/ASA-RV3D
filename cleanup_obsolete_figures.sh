#!/usr/bin/env bash
set -euo pipefail

# Run from ~/RV3D_Public.
# This removes obsolete exploratory / publication-style figures and plot scripts.
# It keeps experiment data, algorithm scripts, scenario-aware figures, and current docs.

if [ ! -d .git ]; then
  echo "error: run this script from the RV3D_Public repository root" >&2
  exit 1
fi

remove_path() {
  local path="$1"
  if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    git rm -r -- "$path"
  elif [ -e "$path" ]; then
    rm -rf -- "$path"
    echo "removed untracked $path"
  else
    echo "skip missing $path"
  fi
}

echo "=== remove obsolete figure directories ==="
remove_path "results/figures/exploratory"

echo
echo "=== remove obsolete summary figures and old figure README ==="
for path in \
  "results/figures/README.md" \
  "results/figures/summary/partition_v2_main_results.svg" \
  "results/figures/summary/partition_v2_summary_table.md" \
  "results/figures/summary/partition_v2_sweep_heatmap.svg" \
  "results/figures/summary/partition_v2_sweep_tradeoff.svg" \
  "results/figures/summary/riscv32i_v2_ablation_summary.svg" \
  "results/figures/summary/riscv_3d_proxy_cost_summary.svg" \
  "results/figures/summary/riscv_3d_proxy_sensitivity.svg" \
  "results/figures/summary/two_riscv_benchmark_partition_summary.svg" \
  "results/figures/summary/two_riscv_multi_metric_summary.svg"; do
  remove_path "$path"
done

echo
echo "=== remove superseded scenario figures ==="
for path in \
  "results/figures/scenario/scenario_architecture_behavior.svg" \
  "results/figures/scenario/scenario_crossing_heatmap.svg"; do
  remove_path "$path"
done

echo
echo "=== remove obsolete plotting scripts ==="
for path in \
  "evaluation/plot_partition_v1.py" \
  "evaluation/plot_partition_v2.py" \
  "evaluation/plot_partition_v2_sweep.py" \
  "evaluation/plot_publication_figures.py" \
  "evaluation/plot_benchmark_summary.py" \
  "evaluation/plot_multi_metric_summary.py" \
  "evaluation/plot_summary_figures.py" \
  "evaluation/regenerate_core_figures.py" \
  "evaluation/plot_3d_proxy_sensitivity_margin.py"; do
  remove_path "$path"
done

echo
echo "=== remove obsolete figure/plot docs ==="
for path in \
  "docs/phase4-visualization-v1.md" \
  "docs/phase4-visualization-v2.md" \
  "docs/phase5-partition-v2-sweep-figures.md" \
  "docs/phase6-publication-figures.md"; do
  remove_path "$path"
done

echo
echo "=== remove stale patch files ==="
find . -maxdepth 2 -type f -name "rv3d_*.patch" -print -delete

echo
echo "=== remaining figure files ==="
find results/figures -type f 2>/dev/null | sort || true

echo
echo "=== git status ==="
git status --short
