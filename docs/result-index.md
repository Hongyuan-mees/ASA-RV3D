# Result Index

This index maps RV3D experiment families to their main outputs, figures, and reproduction entrypoints.
It is intentionally neutral: it supports competition review, repository navigation, and later paper writing.

RV3D is an early-stage RISC-V 3D partitioning research prototype.  The listed metrics are proxy-level evaluation artifacts unless explicitly stated otherwise.

## Main Timing Aware Repair

**Purpose.** Compare TritonPart against ASA-RV3D timing-regret guarded repair across RISC-V cores and 3D partitioning scenarios.

**Interpretation.** Core evidence that ASA-RV3D improves timing-weighted inter-tier crossing over the strong TritonPart baseline.

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

**Interpretation.** Independent proxy validation: lower vertical-delay-induced WNS/TNS degradation indicates better path continuity across tiers.

**Primary outputs.**

- `results/benchmark_summary/path_aware_downstream_vertical_delay_summary.csv` (present)
- `results/benchmark_summary/path_aware_downstream_vertical_delay_rollup.csv` (present)

**Figures.**

- `results/figures/paper/fig5_2_downstream_tns_degradation.svg` (present)

**Entrypoints.**

- `evaluation/evaluate_path_aware_downstream_vertical_delay.py` (present)
- `partition/partition_tritonpart_path_aware_guarded_repair.py` (present)

## Component Ablation

**Purpose.** Separate the contribution of TritonPart, ASA-RV3D without timing guard, timing-regret guard, and path-aware repair.

**Interpretation.** Ablation evidence that timing-regret and path-aware guards optimize different risk views.

**Primary outputs.**

- `results/benchmark_summary/component_ablation_rollup.csv` (present)
- `results/benchmark_summary/component_ablation_timing_crossing_summary.csv` (present)
- `results/benchmark_summary/component_ablation_downstream_summary.csv` (present)

**Figures.**

- `results/figures/paper/fig5_3_component_ablation_timing_crossing.svg` (present)

**Entrypoints.**

- `run_component_ablation.py` (present)

## Robustness Checks

**Purpose.** Check whether downstream conclusions are stable under vertical-delay, path-count, and path-budget variations.

**Interpretation.** Sensitivity evidence that results are not tied to a single vertical-delay or path-count setting.

**Primary outputs.**

- `results/benchmark_summary/path_aware_downstream_delay_sweep_rollup.csv` (present)
- `results/benchmark_summary/path_aware_downstream_pathcount_sweep_rollup.csv` (present)
- `results/benchmark_summary/ibex_path_aware_budget_sensitivity.csv` (present)

**Figures.**

- `results/figures/paper/fig5_4_vertical_delay_sensitivity.svg` (present)
- `results/figures/paper/fig5_4_ibex_path_budget_sensitivity.svg` (present)

**Entrypoints.**

- `run_path_aware_downstream_delay_sweep.py` (present)
- `run_path_aware_downstream_pathcount_sweep.py` (present)
- `partition/partition_tritonpart_path_aware_guarded_repair.py` (present)

## Scenario Behavior Analysis

**Purpose.** Measure how control/datapath, memory-near-logic, and state/clock scenarios change tier assignment behavior under guarded repair.

**Interpretation.** Scenario intent is visible but deliberately conservative because timing and balance guards constrain local moves.

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

**Interpretation.** Pseudo-3D outputs are visualization and proxy-validation artifacts, not signoff 3D P&R.

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

**Interpretation.** Boundary/sanity cases clarify when TritonPart already leaves limited repair opportunity.

**Primary outputs.**

- `results/benchmark_summary/serv_timing_regret_guarded_summary.csv` (present)
- `results/benchmark_summary/scr1_core_tuned_timing_regret_guarded_summary.csv` (present)

**Figures.**

- `results/figures/final/scr1_core_tuned_timing_weighted_crossing.svg` (present)

**Entrypoints.**

- `partition/partition_tritonpart_timing_regret_guarded_repair.py` (present)

## Repository Readiness

**Purpose.** Check that core scripts, summaries, figures, and wording are aligned and avoid overclaiming.

**Interpretation.** Repository hygiene evidence for reproducibility and review readiness.

**Primary outputs.**

- `results/benchmark_summary/paper_readiness_audit.csv` (present)
- `results/benchmark_summary/paper_readiness_audit.md` (present)

**Figures.**

- None

**Entrypoints.**

- `scripts/audit_paper_readiness.py` (present)
