# ASA-RV3D Project Index

This document is the navigation page for RV3D-Public. It lists the current mainline implementation, result files, and documentation after the project moved from standalone scenario-aware partitioning to TritonPart-backed ASA-RV3D guarded repair.

## Project Scope

ASA-RV3D is a lightweight, explainable research prototype for RISC-V architecture-aware 3D tier-partition exploration.

The project does not claim to be a full 3D physical design flow. It focuses on early-stage analysis:

- mapping gate-level RISC-V instances to architecture units,
- evaluating 3D integration scenarios,
- adding graph-context confidence to semantic labels,
- extracting coverage-gated physical-context features from public ORFS/OpenROAD outputs,
- using TritonPart as a mature hypergraph partitioning backend,
- testing whether ASA-RV3D can safely repair TritonPart assignments using architecture/scenario/physical/timing context.

## Main Pipeline

The current mainline pipeline is:

1. Generate public ORFS/OpenROAD baselines.
2. Extract compact gate-level and physical proxy features.
3. Classify and map instances to RISC-V architecture units.
4. Compute graph-context semantic confidence.
5. Diagnose DEF matching and physical observability.
6. Compute coverage-gated physical-context scores.
7. Export a TritonPart hypergraph and import its 2-way partition.
8. Run ASA-RV3D guarded repair over the TritonPart assignment.
9. Evaluate repaired assignments under scenario and physical-augmented objectives.
10. Extract OpenSTA timing context and apply timing-regret guarded repair.

## Key Configuration Files

| Path | Purpose |
| ---- | ------- |
| `configs/riscv_architecture_template.yaml` | RISC-V architecture-unit template used by the mapper. |
| `configs/3d_integration_scenarios.yaml` | Scenario definitions and proxy-cost weights. |

## Main Implementation Files

### Feature Extraction And Mapping

| Path | Purpose |
| ---- | ------- |
| `scripts/extract_orfs_baseline.py` | Extracts compact netlist/report features from ORFS/OpenROAD outputs. |
| `evaluation/extract_physical_features.py` | Extracts DEF placement, HPWL proxy, fanout, and region features. |
| `evaluation/diagnose_def_matching.py` | Diagnoses how well gate-level instances match DEF components. |
| `classifier/architecture_classifier.py` | First-stage rule-based architecture classification. |
| `classifier/architecture_mapper.py` | Maps gate-level instances to formal RISC-V architecture units. |
| `evaluation/graph_context_score.py` | Computes graph-context semantic confidence features. |
| `evaluation/summarize_physical_coverage.py` | Builds physical observability and confidence weights by architecture unit. |
| `evaluation/physical_context_score.py` | Computes coverage-gated physical-context scores. |

### TritonPart Backend Integration

| Path | Purpose |
| ---- | ------- |
| `evaluation/export_tritonpart_hgr.py` | Exports instance-feature CSVs to a TritonPart-compatible hypergraph. |
| `evaluation/import_tritonpart_partition.py` | Converts TritonPart `.part.2` output back to assignment CSV. |

### Partitioning And Repair

| Path | Purpose |
| ---- | ------- |
| `partition/partition_v2.py` | Score-based architecture-aware partitioning baseline. |
| `partition/partition_v3_context.py` | Graph-context enhanced partitioning. |
| `partition/partition_scenario_aware.py` | Scenario-aware tier assignment using 3D scenario objectives. |
| `partition/partition_v4_physical_context.py` | Unguarded physical-context objective variant. |
| `partition/partition_v4b_physical_guarded.py` | Standalone guarded physical-context partitioner. |
| `partition/partition_tritonpart_guarded_repair.py` | Guarded ASA-RV3D repair over TritonPart assignments. |
| `partition/partition_tritonpart_timing_regret_guarded_repair.py` | Current timing-aware mainline: adds explicit timing-regret guard to TritonPart repair. |
| `partition/partition_tritonpart_timing_guarded_repair.py` | Soft timing-weighted ablation; retained because explicit regret guarding performs better. |

### Evaluation And Diagnosis

| Path | Purpose |
| ---- | ------- |
| `evaluation/evaluate_scenario_cost.py` | Evaluates assignments under scenario-specific 3D proxy costs. |
| `evaluation/scenario_transfer_test.py` | Tests whether scenario-specific assignments transfer across scenarios. |
| `evaluation/analyze_scenario_transfer_failures.py` | Explains non-own-best scenario-transfer cases. |
| `evaluation/diagnose_state_clock_structure.py` | Diagnoses whether state/clock units are structurally strong enough. |
| `evaluation/analyze_physical_context.py` | Summarizes high-risk physical-context instances and score buckets. |
| `evaluation/evaluate_v4_physical_comparison.py` | Compares unguarded v4 physical-context assignments against earlier baselines. |
| `evaluation/extract_timing_context.py` | Parses OpenSTA report_checks output into instance-level timing context scores. |
| `evaluation/evaluate_timing_crossing.py` | Measures timing-weighted crossing for TritonPart and repaired assignments. |
| `evaluation/summarize_v4b_guard090_results.py` | Compact audit table for standalone v4b guard090 results. |
| `evaluation/plot_scenario_results.py` | Generates the retained scenario visualization figures. |

## Main Result Files

### TritonPart Backend And Guarded Repair

| Path | Purpose |
| ---- | ------- |
| `results/benchmark_summary/tritonpart_guarded_repair_summary.csv` | Final TritonPart initial vs ASA-RV3D guarded repair summary. |
| `results/benchmark_summary/tritonpart_scenario_cost/` | TritonPart assignment evaluated under scenario costs. |
| `results/ibex_tritonpart_baseline/` | Ibex TritonPart hypergraph, vertex map, and assignment. |
| `results/riscv32i_tritonpart_baseline/` | riscv32i TritonPart hypergraph, vertex map, and assignment. |
| `results/ibex_tritonpart_guarded_repair/` | Ibex ASA-RV3D repair over TritonPart outputs. |
| `results/riscv32i_tritonpart_guarded_repair/` | riscv32i ASA-RV3D repair over TritonPart outputs. |
| `results/benchmark_summary/riscv32i_tritonpart_seed_robustness_summary.csv` | Five-seed robustness check for TritonPart guarded repair on riscv32i state/clock. |

### Timing-Regret Guarded Repair Results

| Path | Description |
| ---- | ----------- |
| `results/timing_reports/` | OpenSTA report_checks, TNS, and WNS reports used for timing context extraction. |
| `results/ibex_features/timing_context_scores.csv` | Ibex instance-level timing context scores. |
| `results/riscv32i_features/timing_context_scores.csv` | riscv32i instance-level timing context scores. |
| `results/picorv32_features/` | PicoRV32 feature extraction, architecture mapping, physical context, and timing context outputs. |
| `results/picorv32_tritonpart_baseline/` | PicoRV32 TritonPart hypergraph, vertex map, and assignment. |
| `results/picorv32_tritonpart_timing_regret_guarded_repair/` | PicoRV32 timing-regret guarded repair outputs. |
| `results/serv_features/` | SERV feature extraction, architecture mapping, physical context, and timing context outputs. |
| `results/serv_tritonpart_baseline/` | SERV TritonPart hypergraph, vertex map, and assignment. |
| `results/serv_tritonpart_timing_regret_guarded_repair/` | SERV timing-regret guarded repair outputs used as a boundary benchmark. |
| `results/ibex_tritonpart_timing_regret_guarded_repair/` | Ibex timing-regret guarded repair outputs. |
| `results/riscv32i_tritonpart_timing_regret_guarded_repair/` | riscv32i timing-regret guarded repair outputs. |
| `results/benchmark_summary/timing_regret_guarded_summary.csv` | Initial state/clock timing-regret improvement summary. |
| `results/benchmark_summary/timing_regret_guarded_all_scenarios_summary.csv` | Earlier two-design all-scenario timing-regret improvement summary. |
| `results/benchmark_summary/timing_regret_guarded_three_riscv_summary.csv` | Current three-RISC-V all-scenario timing-regret improvement summary. |
| `results/benchmark_summary/serv_timing_regret_guarded_summary.csv` | SERV boundary benchmark summary; objective improves while timing-weighted crossing is nearly unchanged. |
| `results/benchmark_summary/timing_regret_crossing/` | Per-design, per-scenario timing crossing diagnostics. |
| `results/benchmark_summary/ibex_timing_regret_guarded_crossing_summary.csv` | Ibex independent timing-crossing diagnostic. |
| `results/benchmark_summary/riscv32i_timing_regret_guarded_crossing_summary.csv` | riscv32i independent timing-crossing diagnostic. |

### Standalone ASA-RV3D Physical-Context Results

| Path | Purpose |
| ---- | ------- |
| `results/benchmark_summary/v4b_guard090_summary.csv` | Standalone scenario-aware vs guarded physical-context audit table. |
| `results/benchmark_summary/v4_physical_comparison.csv` | v3/scenario-aware/v4 comparison under physical-augmented objective. |
| `results/ibex_partition_v4b_physical_guard090/` | Standalone guarded physical-context Ibex outputs. |
| `results/riscv32i_partition_v4b_physical_guard090/` | Standalone guarded physical-context riscv32i outputs. |

### Physical Context And Observability

| Path | Purpose |
| ---- | ------- |
| `results/benchmark_summary/physical_coverage_summary.csv` | Design-level and unit-level physical observability summary. |
| `results/benchmark_summary/physical_coverage_recommendations.csv` | Physical-score usage recommendation by unit. |
| `results/benchmark_summary/physical_context_unit_ranking.csv` | Unit-level physical-context ranking. |
| `results/benchmark_summary/physical_context_top_instances.csv` | Highest physical-risk instances. |
| `results/benchmark_summary/physical_context_score_buckets.csv` | Score-bucket sanity check. |

### Scenario And Diagnosis Results

| Path | Purpose |
| ---- | ------- |
| `results/benchmark_summary/scenario_aware_partition_summary.csv` | Previous scenario-aware partition result. |
| `results/benchmark_summary/scenario_aware_vs_v3_summary.csv` | Scenario-aware vs v3_context comparison. |
| `results/benchmark_summary/scenario_transfer_best_summary.csv` | Best assignment under each scenario-transfer evaluation. |
| `results/benchmark_summary/state_clock_diagnosis_summary.csv` | Structural summary of state/clock signal strength. |
| `results/benchmark_summary/state_clock_diagnosis_crossing.csv` | Crossing dominance by architecture unit. |

## Retained Figures

The retained figures are intentionally limited to high-information scenario results.

| Path | Purpose |
| ---- | ------- |
| `results/figures/scenario/scenario_aware_main_results.svg` | Main scenario-aware objective and balance result. |
| `results/figures/scenario/scenario_architecture_migration.svg` | Architecture units that migrate across scenarios. |
| `results/figures/scenario/scenario_crossing_heatmap_ibex.svg` | Ibex scenario crossing bottleneck heatmap. |
| `results/figures/scenario/scenario_crossing_heatmap_riscv32i.svg` | riscv32i scenario crossing bottleneck heatmap. |
| `results/figures/summary/asa_rv3d_method_flow.svg` | Method flow diagram. |
| `results/figures/core/v4b_guard090_objective_reduction.svg` | Standalone v4b objective-reduction audit figure. |
| `results/figures/core/v4b_guard090_balance_guard.svg` | Standalone v4b balance-guard audit figure. |

## Documentation

| Path | Purpose |
| ---- | ------- |
| `README.md` | Top-level project summary. |
| `docs/asa-rv3d-method.md` | Method description. |
| `docs/experiment-summary.md` | Experiment overview. |
| `docs/related-work-positioning.md` | Related-work boundary and contribution positioning. |
| `docs/scenario-transfer-analysis.md` | Scenario-transfer interpretation. |
| `docs/state-clock-diagnosis.md` | State/clock structural diagnosis. |
| `docs/project-index.md` | This navigation page. |

## Repository Cleanup Note

- Early standalone v1/v2 result directories were removed to keep the repository focused. The corresponding scripts remain as historical ablation code, but the retained evidence now centers on TritonPart-backed guarded and timing-regret repair.

## Main Claims Supported By Current Data

Current results support these claims:

- TritonPart is a much stronger raw cut backend than the standalone ASA-RV3D heuristic.
- Physical guarded repair improves the TritonPart physical-augmented objective across the original six Ibex/riscv32i cases and is retained as an ablation.
- Timing-regret guarded repair reduces timing-weighted crossing versus the previous guarded repair in all nine tested design-scenario cases.
- The repair layer trades tiny raw-cut changes for lower architecture/scenario/physical objective while preserving balance guardrails.
- Architecture semantics, graph confidence, scenario costs, and coverage-gated physical context provide useful signals beyond pure connectivity.

Current results do not support these claims:

- full 3D physical-design signoff,
- signoff timing closure improvement,
- thermal improvement,
- true TSV or hybrid-bond count reduction,
- superiority over GNN-based or industrial 3D partitioners,
- raw-cut superiority over TritonPart.

## Recommended Entry Points

For a quick overview:

1. `README.md`
2. `docs/project-index.md`
3. `docs/experiment-summary.md`
4. `docs/related-work-positioning.md`
5. `docs/scenario-transfer-analysis.md`

For reproducing the current main results:

1. Generate or reuse ORFS/OpenROAD baseline outputs.
2. Run `scripts/extract_orfs_baseline.py`.
3. Run `classifier/architecture_classifier.py`.
4. Run `classifier/architecture_mapper.py`.
5. Run `evaluation/graph_context_score.py`.
6. Run physical feature extraction, DEF matching diagnosis, coverage summarization, and physical-context scoring.
7. Run `evaluation/export_tritonpart_hgr.py`, OpenROAD/TritonPart, and `evaluation/import_tritonpart_partition.py`.
8. Run `partition/partition_tritonpart_guarded_repair.py`.
9. Run OpenSTA timing report extraction, `evaluation/extract_timing_context.py`, and `partition/partition_tritonpart_timing_regret_guarded_repair.py`.
9. Inspect `results/benchmark_summary/tritonpart_guarded_repair_summary.csv`.

<!-- ASA-RV3D-SCR1-INDEX:START -->
## SCR1 Tuned Benchmark Assets

| Path | Purpose |
| --- | --- |
| `results/scr1_core_tuned_features/` | SCR1 tuned extracted netlist, architecture, graph, physical, and timing context features. |
| `results/scr1_core_tuned_tritonpart_baseline/` | SCR1 tuned TritonPart hypergraph, vertex map, and imported assignment. |
| `results/scr1_core_tuned_tritonpart_timing_regret_guarded_repair/` | SCR1 tuned ASA-RV3D timing-regret guarded repair outputs for all scenarios. |
| `results/benchmark_summary/scr1_core_tuned_timing_regret_guarded_summary.csv` | SCR1 tuned three-scenario timing-regret summary. |
| `results/benchmark_summary/timing_regret_guarded_four_riscv_summary.csv` | Four-core headline timing-regret summary. |
| `results/figures/final/four_riscv_timing_weighted_crossing.svg` | Four-core timing-weighted crossing comparison figure. |

<!-- ASA-RV3D-SCR1-INDEX:END -->
