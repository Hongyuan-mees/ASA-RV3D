# Phase 3 Partition V2

Partition v2 upgrades the fixed rule-based tier assignment from partition v1 into a score-based local-refinement heuristic.

## Motivation

Partition v1 showed that an architecture-aware policy can reduce crossing communication proxy, but the method was still a direct class-to-tier mapping. Partition v2 makes the method more algorithmic by optimizing an explicit objective:

```text
objective = crossing proxy
          + instance-balance penalty
          + proxy-weight-balance penalty
          + architecture-placement penalty
```

The method starts from the architecture-aware v1 assignment, then tries single-instance moves. A move is accepted only if it improves the objective.

By default, local refinement also enforces:

```text
minimum instance balance ratio = 0.80
minimum proxy-weight balance ratio = 0.95
```

This prevents the optimizer from reducing crossing proxy by collapsing too much logic onto one tier.

## Run

On the cloud server:

```bash
cd ~/RV3D_Public
python3 partition/partition_v2.py \
  --features-dir results/ibex_features \
  --output-dir results/partition_v2
```

Expected outputs:

```text
results/partition_v2/
├── architecture_aware_v1_assignment.csv
├── architecture_score_v2_assignment.csv
├── class_tier_distribution.csv
├── generic_balance_assignment.csv
├── local_refinement_trace.csv
├── manifest.json
├── partition_comparison.csv
└── top_crossing_nets.csv
```

## Compared Strategies

`generic_balance`

- Architecture-oblivious greedy load balancing.

`architecture_aware_v1`

- Fixed architecture class to tier mapping.
- Reproduces the partition v1 method inside the v2 experiment.

`architecture_score_v2`

- Starts from `architecture_aware_v1`.
- Uses an objective with crossing, balance, and architecture terms.
- Performs greedy local refinement by moving instances when the objective improves.

## Interpretation

The best outcome is not necessarily the lowest crossing number alone. A useful v2 result should preserve the architecture-aware crossing reduction while improving raw instance balance or showing a clearer tradeoff curve.

If v2 improves all metrics, it becomes the main method. If v2 trades one metric for another, it becomes an ablation that demonstrates how crossing, balance, and architecture bias interact.
