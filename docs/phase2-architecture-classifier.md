# Phase 2 Architecture Classifier

The first feature extractor produces gate-level CSV files from the clean ORFS Ibex baseline. The architecture classifier adds a transparent, rule-based mapping from extracted instances to coarse RISC-V / Ibex architecture groups.

This is not intended to be a final semantic reconstruction of the RTL hierarchy. It is a reproducible first pass that creates architecture-aware features for the partitioning experiments.

## Run

On the cloud server:

```bash
cd ~/RV3D_Public
python3 classifier/architecture_classifier.py --features-dir results/ibex_features
```

Expected additional outputs:

```text
results/ibex_features/
├── architecture_classifier_manifest.json
├── architecture_instance_classes.csv
└── architecture_summary.csv
```

## Current Classes

The classifier currently recognizes:

- `clock_reset`
- `register_file`
- `csr`
- `fetch`
- `decode_control`
- `execute_alu`
- `multdiv`
- `load_store`
- `trap_debug`
- `pipeline_state`
- `generated_datapath`
- `generated_control`
- `unclassified`

Rules are intentionally visible in `classifier/architecture_classifier.py` so the report can explain exactly how labels were assigned.

## Interpretation

The ORFS final netlist is mostly flattened and synthesized, so perfect RTL-level classification is not expected from `6_final.v` alone. The useful question for this project is whether lightweight architecture-aware labels can guide 2-tier partitioning better than a generic graph-only baseline.

The next improvement is to combine this rule-based pass with ORFS intermediate files that preserve more hierarchy or signal names.
