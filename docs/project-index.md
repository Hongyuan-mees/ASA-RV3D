# ASA-RV3D Project Index

This document is the navigation page for the RV3D-Public repository.  It lists the current mainline implementation, result files, and documentation after removing obsolete exploratory figures.

## Project Scope

ASA-RV3D is a lightweight, explainable research prototype for RISC-V architecture-aware and scenario-aware 3D tier-partition exploration.

The project does not claim to be a full 3D physical design tool.  It focuses on early-stage analysis:

- mapping gate-level RISC-V instances to architecture units,
- evaluating 3D integration scenarios,
- comparing generic, graph-context, and scenario-aware partitioning,
- diagnosing when scenario-specific objectives are or are not structurally meaningful.

## Main Pipeline

The current mainline pipeline is:

1. Generate public ORFS/OpenROAD baselines.
2. Extract compact gate-level features.
3. Classify and map instances to RISC-V architecture units.
4. Compute graph-context semantic confidence.
5. Run v2/v3 and scenario-aware tier partitioning.
6. Evaluate generic, graph-context, scenario-aware, and scenario-transfer results.
7. Diagnose state/clock structural limitations.

## Key Configuration Files

| Path | Purpose |
| ---- | ------- |
| `configs/riscv_architecture_template.yaml` | RISC-V architecture-unit template used by the mapper. |
| `configs/3d_integration_scenarios.yaml` | Scenario definitions and proxy-cost weights. |

## Main Implementation Files

### Feature Extraction And Mapping

| Path | Purpose |
| ---- | ------- |
| `scripts/extract_orfs_baseline.py` | Extracts compact features from ORFS/OpenROAD outputs. |
| `classifier/architecture_classifier.py` | First-stage rule-based architecture classification. |
| `classifier/architecture_mapper.py` | Maps gate-level instances to formal RISC-V architecture units. |
| `evaluation/graph_context_score.py` | Computes graph-context semantic confidence features. |

### Partitioning

| Path | Purpose |
| ---- | ------- |
| `partition/partition_v2.py` | Score-based architecture-aware partitioning baseline. |
| `partition/partition_v3_context.py` | Graph-context enhanced partitioning. |
| `partition/partition_scenario_aware.py` | Scenario-aware tier assignment using 3D scenario objectives. |

### Evaluation And Diagnosis

| Path | Purpose |
| ---- | ------- |
| `evaluation/evaluate_scenario_cost.py` | Evaluates assignments under scenario-specific 3D proxy costs. |
| `evaluation/scenario_transfer_test.py` | Tests whether scenario-specific assignments transfer across scenarios. |
| `evaluation/analyze_scenario_transfer_failures.py` | Explains non-own-best scenario-transfer cases. |
| `evaluation/diagnose_state_clock_structure.py` | Diagnoses whether state/clock units are structurally strong enough. |
| `evaluation/summarize_scenario_vs_v3.py` | Compares scenario-aware partitioning against v3_context. |
| `evaluation/plot_scenario_results.py` | Generates the retained scenario visualization figures. |

## Main Result Files

### Benchmark Summaries

| Path | Purpose |
| ---- | ------- |
| `results/benchmark_summary/two_riscv_benchmark_partition_summary.csv` | Generic/v1/v2 summary for Ibex and riscv32i. |
| `results/benchmark_summary/two_riscv_extended_baseline_summary.csv` | Extended baseline comparison. |
| `results/benchmark_summary/riscv_3d_proxy_cost_summary.csv` | 3D proxy cost summary. |
| `results/benchmark_summary/scenario_aware_partition_summary.csv` | Main scenario-aware partition result. |
| `results/benchmark_summary/scenario_aware_vs_v3_summary.csv` | Scenario-aware vs v3_context comparison. |
| `results/benchmark_summary/scenario_transfer_best_summary.csv` | Best assignment under each scenario-transfer evaluation. |
| `results/benchmark_summary/scenario_transfer_matrix.csv` | Full scenario-transfer matrix. |

### Scenario Diagnosis

| Path | Purpose |
| ---- | ------- |
| `results/benchmark_summary/scenario_transfer_failure_analysis.csv` | Objective and balance gaps for non-own-best cases. |
| `results/benchmark_summary/scenario_transfer_failure_unit_cost_delta.csv` | Unit-level cost deltas for non-own-best cases. |
| `results/benchmark_summary/scenario_transfer_failure_tier_delta.csv` | Unit-level tier movement deltas. |
| `results/benchmark_summary/state_clock_diagnosis_summary.csv` | Structural summary of state/clock signal strength. |
| `results/benchmark_summary/state_clock_diagnosis_units.csv` | Unit-level state/clock diagnosis. |
| `results/benchmark_summary/state_clock_diagnosis_crossing.csv` | Crossing dominance by architecture unit. |

### Feature And Assignment Outputs

| Path | Purpose |
| ---- | ------- |
| `results/ibex_features/` | Ibex extracted features, architecture mapping, and graph context. |
| `results/riscv32i_features/` | riscv32i extracted features, architecture mapping, and graph context. |
| `results/ibex_partition_v3_context/` | Ibex v3 graph-context partition results. |
| `results/riscv32i_partition_v3_context/` | riscv32i v3 graph-context partition results. |
| `results/ibex_scenario_partition/` | Ibex scenario-aware partition outputs. |
| `results/riscv32i_scenario_partition/` | riscv32i scenario-aware partition outputs. |

## Retained Figures

The retained figures are intentionally limited to high-information scenario results.

| Path | Purpose |
| ---- | ------- |
| `results/figures/scenario/scenario_aware_main_results.svg` | Main scenario-aware objective and balance result. |
| `results/figures/scenario/scenario_architecture_migration.svg` | Architecture units that migrate across scenarios. |
| `results/figures/scenario/scenario_crossing_heatmap_ibex.svg` | Ibex scenario crossing bottleneck heatmap. |
| `results/figures/scenario/scenario_crossing_heatmap_riscv32i.svg` | riscv32i scenario crossing bottleneck heatmap. |
| `results/figures/summary/asa_rv3d_method_flow.svg` | Method flow diagram. |

## Documentation

| Path | Purpose |
| ---- | ------- |
| `README.md` | Top-level project summary. |
| `docs/asa-rv3d-method.md` | Method description. |
| `docs/experiment-summary.md` | Experiment overview. |
| `docs/two-riscv-benchmark-results.md` | Two-benchmark result interpretation. |
| `docs/related-work-positioning.md` | Related-work boundary and contribution positioning. |
| `docs/scenario-transfer-analysis.md` | Scenario-transfer interpretation. |
| `docs/state-clock-diagnosis.md` | State/clock structural diagnosis. |
| `docs/project-index.md` | This navigation page. |

## Main Claims Supported By Current Data

Current results support these claims:

- Scenario-aware partitioning improves over generic and v3_context baselines under scenario-specific proxy objectives.
- Scenario transfer tests show that scenario-specific assignments are often best or near-best under their intended objective.
- Non-own-best cases are explainable and mostly dominated by flexible generated control/datapath logic.
- State/Clock protected behavior is structurally meaningful for Ibex but weaker for riscv32i under the current gate-level proxy model.

Current results do not support these claims:

- full 3D physical-design signoff,
- timing closure improvement,
- thermal improvement,
- true TSV or hybrid-bond count reduction,
- superiority over GNN-based or industrial 3D partitioners.

## Recommended Entry Points

For a quick overview:

1. `README.md`
2. `docs/project-index.md`
3. `docs/related-work-positioning.md`
4. `docs/scenario-transfer-analysis.md`
5. `docs/state-clock-diagnosis.md`

For reproducing the current main results:

1. Generate or reuse ORFS/OpenROAD baseline outputs.
2. Run `scripts/extract_orfs_baseline.py`.
3. Run `classifier/architecture_classifier.py`.
4. Run `classifier/architecture_mapper.py`.
5. Run `evaluation/graph_context_score.py`.
6. Run `partition/partition_scenario_aware.py`.
7. Run `evaluation/evaluate_scenario_cost.py`.
8. Run `evaluation/scenario_transfer_test.py`.
9. Run `evaluation/diagnose_state_clock_structure.py`.

