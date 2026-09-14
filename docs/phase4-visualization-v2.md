# Phase 4 Visualization V2

This phase adds report figures for the score-based partition v2 experiment.

## Run

On the cloud server:

```bash
cd ~/RV3D_Public
python3 evaluation/plot_partition_v2.py \
  --partition-dir results/partition_v2 \
  --output-dir results/figures
```

Expected outputs:

```text
results/figures/
├── partition_v2_balance.svg
├── partition_v2_class_distribution.svg
└── partition_v2_crossing_metrics.svg
```

## Intended Use

Use the v2 figures as the main report figures because they compare all three strategies:

- `generic_balance`
- `architecture_aware_v1`
- `architecture_score_v2`

The v1 figures can remain as intermediate development evidence. The v2 crossing plot is the main result figure.
