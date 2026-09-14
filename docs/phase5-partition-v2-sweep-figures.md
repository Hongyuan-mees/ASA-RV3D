# Phase 5 Partition V2 Sweep Figures

This phase visualizes the partition v2 parameter sweep.

## Run

On the cloud server:

```bash
cd ~/RV3D_Public
python3 evaluation/plot_partition_v2_sweep.py \
  --sweep-dir results/partition_v2_sweep \
  --output-dir results/figures
```

Expected outputs:

```text
results/figures/
├── partition_v2_sweep_reduction_vs_generic.svg
├── partition_v2_sweep_reduction_vs_v1.svg
└── partition_v2_sweep_tradeoff.svg

results/partition_v2_sweep/sweep_report_table.md
```

## Intended Use

Use these figures to support the claim that partition v2 is robust to reasonable parameter changes.

- The generic heatmap shows whether v2 consistently improves over architecture-oblivious balancing.
- The v1 heatmap shows whether score-based refinement consistently improves over fixed architecture mapping.
- The tradeoff plot shows the relationship between proxy-weight balance and crossing reduction.
