# Phase 6 Summary Figures

This phase creates cleaner figures intended for reports or reports.

The earlier SVG plots are useful for debugging, but some labels overlap and the visual hierarchy is not ideal for summary. The summary figure script creates larger, cleaner SVGs with fewer labels and clearer narrative roles.

## Run

On the cloud server:

```bash
cd ~/RV3D_Public
python3 evaluation/plot_summary_figures.py \
  --partition-dir results/partition_v2 \
  --sweep-dir results/partition_v2_sweep \
  --output-dir results/figures_report
```

Expected outputs:

```text
results/figures_report/
├── report_main_partition_results.svg
├── report_sweep_reduction_heatmap.svg
├── report_sweep_tradeoff.svg
└── report_summary_table.md
```

## Figure Roles

`report_main_partition_results.svg`

- Main result figure.
- Shows crossing connection proxy reduction and balance ratios in one two-panel figure.

`report_sweep_reduction_heatmap.svg`

- Robustness figure.
- Shows that v2 improves over generic balancing across architecture-weight and balance-threshold settings.

`report_sweep_tradeoff.svg`

- Tradeoff figure.
- Shows proxy-weight balance versus crossing reduction and labels only key operating points.

`report_summary_table.md`

- Small table for the report text.
- Highlights best reduction, default conservative setting, and strict-balance best setting.
