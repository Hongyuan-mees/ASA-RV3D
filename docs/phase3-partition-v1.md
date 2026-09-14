# Phase 3 Partition V1

This phase creates the first reproducible 2-tier partitioning comparison.

It is intentionally lightweight: the goal is to produce a clean experiment table before integrating a heavier partition backend.

## Inputs

The script consumes Phase 2 outputs:

- `results/ibex_features/instance_features.csv`
- `results/ibex_features/architecture_instance_classes.csv`

## Run

On the cloud server:

```bash
cd ~/RV3D_Public
python3 partition/partition_v1.py \
  --features-dir results/ibex_features \
  --output-dir results/partition_v1
```

Expected outputs:

```text
results/partition_v1/
├── architecture_aware_assignment.csv
├── class_tier_distribution.csv
├── generic_balance_assignment.csv
├── manifest.json
├── partition_comparison.csv
└── top_crossing_nets.csv
```

## Strategies

`generic_balance`

- Architecture-oblivious greedy balancing.
- Sorts instances by proxy weight and assigns each to the currently lighter tier.
- Serves as the generic two-way baseline.

`architecture_aware`

- Uses architecture labels from `classifier/architecture_classifier.py`.
- Places control/front-end style classes on `tier0`.
- Places datapath/back-end style classes on `tier1`.
- Balances only classes without an explicit policy.

Current policy:

```text
tier0: clock_reset, fetch, decode_control, csr, trap_debug, pipeline_state, generated_control
tier1: execute_alu, multdiv, load_store, register_file, generated_datapath
```

## Metrics

The first-pass metrics are proxy metrics:

- tier instance balance
- tier proxy-weight balance
- crossing net count
- crossing connection proxy
- class distribution across tiers
- top crossing nets

The crossing metrics do not yet use Liberty pin directions or real 3D placement. They are meant to rank and debug partition policies before introducing heavier EDA backends.
