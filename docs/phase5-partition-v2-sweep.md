# Phase 5 Partition V2 Parameter Sweep

This phase checks whether the score-based partition v2 result is robust to reasonable parameter changes.

## Run

On the cloud server:

```bash
cd ~/RV3D_Public
python3 evaluation/sweep_partition_v2.py \
  --features-dir results/ibex_features \
  --output-dir results/partition_v2_sweep
```

The default sweep covers:

```text
architecture_weight = 0.1, 0.2, 0.4, 0.8
min_weight_balance = 0.90, 0.95, 0.98
```

Expected main output:

```text
results/partition_v2_sweep/sweep_summary.csv
```

Each individual run is also saved under:

```text
results/partition_v2_sweep/arch*_wb*/
```

## Why This Matters

The main v2 result should not depend on one fragile hand-picked parameter setting. The sweep checks whether crossing reduction remains strong when architecture bias and balance constraints vary.

Useful report questions:

- Is v2 consistently better than generic balancing?
- Is v2 consistently better than the fixed architecture-aware v1 policy?
- How does stricter weight balance affect crossing reduction?
- Does increasing architecture weight preserve more class purity at the cost of crossing?
