# Phase 4 Visualization V1

This phase turns partition CSV outputs into report-ready figures.

The plotting script intentionally writes SVG using only Python's standard library. This avoids adding plotting dependencies to the cloud server.

## Run

On the cloud server:

```bash
cd ~/RV3D_Public
python3 evaluation/plot_partition_v1.py \
  --partition-dir results/partition_v1 \
  --output-dir results/figures
```

Expected outputs:

```text
results/figures/
├── partition_v1_balance.svg
├── partition_v1_class_distribution.svg
└── partition_v1_crossing_metrics.svg
```

## Figures

`partition_v1_crossing_metrics.svg`

- Compares crossing net count and crossing connection proxy.
- Main result: architecture-aware partitioning reduces crossing communication proxy compared with generic balancing.

`partition_v1_balance.svg`

- Compares raw instance balance and proxy-weight balance.
- Main result: architecture-aware partitioning sacrifices instance-count symmetry but preserves proxy-weight balance.

`partition_v1_class_distribution.svg`

- Shows where architecture classes are placed in the architecture-aware policy.
- Useful for explaining the method, not just the final metric.
