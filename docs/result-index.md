# Historical Development Result Index

This generated index documents retained development and historical experiment families. It is not the source of truth for the final manuscript tables. For paper-facing results and provenance, see `README.md` and `paper/`.

The listed metrics are proxy-level evaluation artifacts unless explicitly stated otherwise.

## Main Timing Aware Repair

**Purpose.** Compare TritonPart against ASA-RV3D timing-regret guarded repair across RISC-V cores and 3D partitioning scenarios.

**Interpretation.** Retained historical evidence for timing-weighted inter-tier crossing reduction over TritonPart-derived assignments.

**Primary outputs.**

- `results/benchmark_summary/timing_regret_guarded_all_scenarios_summary.csv` (present)
- `results/benchmark_summary/timing_regret_guarded_three_riscv_summary.csv` (present)

**Figures.**

- `results/figures/paper/fig5_1_timing_weighted_crossing.svg` (present)

**Entrypoints.**

- `partition/partition_tritonpart_timing_regret_guarded_repair.py` (present)
- `scripts/reproduce_core_results.sh` (present)

## Downstream Vertical Delay Proxy

**Purpose.** Estimate downstream timing impact by adding fixed vertical-link delay on OpenSTA paths for TritonPart, ASA-RV3D, and path-aware ASA-RV3D assignments.

**Interpretation.** Retained path-level proxy validation for vertical-link-delay sensitivity.

**Primary outputs.**

- `results/benchmark_summary/path_aware_downstream_vertical_delay_summary.csv` (present)
- `results/benchmark_summary/path_aware_downstream_vertical_delay_rollup.csv` (present)

**Figures.**

- `results/figures/paper/fig5_2_downstream_tns_degradation.svg` (present)

**Entrypoints.**

- `evaluation/evaluate_path_aware_downstream_vertical_delay.py` (present)
- `partition/partition_tritonpart_path_aware_guarded_repair.py` (present)

## Component Ablation

**Purpose.** Separate the contribution of TritonPart, ASA-RV3D without timing guard, timing-regret guard, path-aware repair, and architecture semantics.

**Interpretation.** Retained ablation evidence for complementary objective and guard components.

**Primary outputs.**

- `results/benchmark_summary/component_ablation_rollup.csv` (present)
- `results/benchmark_summary/component_ablation_timing_crossing_summary.csv` (present)
- `results/benchmark_summary/component_ablation_downstream_summary.csv` (present)
- `results/benchmark_summary/architecture_ablation_rollup.csv` (present)
- `results/benchmark_summary/architecture_ablation_summary.csv` (present)

**Figures.**

- `results/figures/paper/fig5_3_component_ablation_timing_crossing.svg` (present)

**Entrypoints.**

- `scripts/run_component_ablation.py` (present)
- `scripts/run_architecture_ablation.py` (present)

## Baseline Feasibility

**Purpose.** Track OpenROAD native triton_part_design timing-aware baseline feasibility and partial comparison against ASA-RV3D.

**Interpretation.** Historical baseline-feasibility tracking for OpenROAD native timing-aware TritonPart runs.

**Primary outputs.**

- `results/benchmark_summary/tritonpart_design_timing_aware_baseline_rollup.csv` (present)
- `results/benchmark_summary/tritonpart_design_timing_aware_baseline_summary.csv` (present)
- `results/benchmark_summary/riscv32i_tritonpart_design_timing_aware_crossing.csv` (present)
- `results/benchmark_summary/picorv32_tritonpart_design_timing_aware_crossing.csv` (present)
- `results/benchmark_summary/scr1_core_tuned_tritonpart_design_timing_aware_crossing.csv` (present)

**Figures.**

- None

**Entrypoints.**

- `scripts/probe_tritonpart_design_timing_aware.sh` (present)
- `scripts/import_tritonpart_design_solution.py` (present)
- `scripts/summarize_tritonpart_design_timing_aware_baseline.py` (present)

## Robustness Checks

**Purpose.** Check whether downstream conclusions are stable under vertical-delay, path-count, and path-budget variations.

**Interpretation.** Retained sensitivity checks for vertical-delay and path-count assumptions.

**Primary outputs.**

- `results/benchmark_summary/path_aware_downstream_delay_sweep_rollup.csv` (present)
- `results/benchmark_summary/path_aware_downstream_pathcount_sweep_rollup.csv` (present)
- `results/benchmark_summary/ibex_path_aware_budget_sensitivity.csv` (present)

**Figures.**

- `results/figures/paper/fig5_4_vertical_delay_sensitivity.svg` (present)
- `results/figures/paper/fig5_4_ibex_path_budget_sensitivity.svg` (present)

**Entrypoints.**

- `scripts/run_path_aware_downstream_delay_sweep.py` (present)
- `scripts/run_path_aware_downstream_pathcount_sweep.py` (present)
- `partition/partition_tritonpart_path_aware_guarded_repair.py` (present)

## Scenario Behavior Analysis

**Purpose.** Measure how control/datapath, memory-near-logic, and state/clock scenarios change tier assignment behavior under guarded repair.

**Interpretation.** Retained development analysis of scenario-dependent behavior.

**Primary outputs.**

- `results/benchmark_summary/scenario_behavior_rollup.csv` (present)
- `results/benchmark_summary/scenario_behavior_paper_summary.csv` (present)
- `results/benchmark_summary/scenario_behavior_top_unit_changes.csv` (present)

**Figures.**

- None

**Entrypoints.**

- `evaluation/analyze_scenario_behavior.py` (present)
- `evaluation/summarize_scenario_behavior.py` (present)

## Pseudo3D Realization

**Purpose.** Export pseudo-3D tier-layout artifacts and vertical-link candidates for early 3D-aware validation and presentation.

**Interpretation.** Visualization and proxy-validation artifacts, not signoff 3-D place-and-route.

**Primary outputs.**

- `results/benchmark_summary/pseudo3d_realization_rollup.csv` (present)
- `results/benchmark_summary/pseudo3d_realization_summary.csv` (present)
- `results/benchmark_summary/pseudo3d_layout_summary.csv` (present)

**Figures.**

- None

**Entrypoints.**

- `evaluation/evaluate_pseudo3d_realization.py` (present)
- `evaluation/export_pseudo3d_layout.py` (present)

## Boundary Cases

**Purpose.** Track designs where the improvement space is limited or neutral, strengthening the credibility of the evaluation.

**Interpretation.** Boundary/sanity cases retained to show limited or neutral repair opportunity.

**Primary outputs.**

- `results/benchmark_summary/serv_timing_regret_guarded_summary.csv` (present)
- `results/benchmark_summary/scr1_core_tuned_timing_regret_guarded_summary.csv` (present)

**Figures.**

- `results/figures/final/scr1_core_tuned_timing_weighted_crossing.svg` (present)

**Entrypoints.**

- `partition/partition_tritonpart_timing_regret_guarded_repair.py` (present)

## Dynamic Constrained Asa Phase3

**Purpose.** Evaluate dynamic TritonPart-compatible ASA local refinement on native timing-aware TritonPart assignments under area, cut, path, and timing-weighted guards.

**Interpretation.** Retained Phase-3 development evidence for constrained local refinement.

**Primary outputs.**

- `results/benchmark_summary/dynamic_constrained_asa_phase3_rollup.csv` (present)
- `results/benchmark_summary/dynamic_constrained_asa_phase3_summary.csv` (present)

**Figures.**

- None

**Entrypoints.**

- `partition/partition_tritonpart_compatible_dynamic_guarded_repair.py` (present)
- `scripts/select_dynamic_checkpoint_with_canonical_timing.py` (present)
- `scripts/run_dynamic_canonical_checkpoint_selection.sh` (present)
- `scripts/summarize_dynamic_constrained_asa_phase3.py` (present)

## Dynamic Architecture Ablation Phase3

**Purpose.** Compare dynamic constrained refinement with architecture semantics enabled versus disabled under the same area, cut, path, and timing-weighted guards.

**Interpretation.** Retained architecture-ablation development evidence; not the final manuscript source of truth.

**Primary outputs.**

- `results/benchmark_summary/dynamic_architecture_ablation_phase3_rollup.csv` (present)
- `results/benchmark_summary/dynamic_architecture_ablation_phase3_summary.csv` (present)

**Figures.**

- None

**Entrypoints.**

- `scripts/run_dynamic_architecture_off_phase3.sh` (present)
- `scripts/summarize_dynamic_architecture_ablation_phase3.py` (present)

## Repository Readiness

**Purpose.** Check that core scripts, summaries, figures, and wording are aligned and avoid overclaiming.

**Interpretation.** Historical repository hygiene audit retained for development traceability.

**Primary outputs.**

- `results/benchmark_summary/paper_readiness_audit.csv` (present)
- `results/benchmark_summary/paper_readiness_audit.md` (present)

**Figures.**

- None

**Entrypoints.**

- `scripts/audit_paper_readiness.py` (present)
