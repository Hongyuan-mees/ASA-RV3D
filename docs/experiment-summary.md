# Experiment Summary

This document summarizes the current ASA-RV3D experimental evidence.

ASA-RV3D is an architecture-semantic-aware tier partitioning prototype for RISC-V gate-level designs. The current evaluation focuses on whether architecture semantics and graph-context confidence can reduce inter-tier crossing proxy while preserving usable tier balance.

## Benchmark Set

| Design | Source Flow | Platform | Instances | Baseline Status | Route DRC Lines |
| --- | --- | --- | ---: | --- | ---: |
| Ibex | ORFS/OpenROAD | sky130hd | 15601 | clean | 0 |
| riscv32i | ORFS/OpenROAD | sky130hd | 5737 | clean | 0 |

The repository stores compact CSV/JSON/SVG summaries. Large ORFS physical artifacts such as DEF, GDS, ODB, SPEF, and full logs are kept outside Git.

## Compared Methods

| Method | Meaning |
| --- | --- |
| `generic_balance` | Baseline that balances instances and proxy weights without architecture semantics. |
| `architecture_aware_v1` | Direct architecture-guided assignment. Useful but often imbalanced. |
| `architecture_score_v2` | Balance-aware local refinement with architecture penalty. Main stable method. |
| `connectivity_only` | Connectivity-driven refinement without full architecture guidance. |
| `v3_context` | Graph-context version that scales architecture guidance by semantic confidence. |

## Main V2 Results

Lower `crossing_connections_proxy` is better.

| Design | Generic Crossing | V1 Crossing | V2 Crossing | V2 Reduction vs Generic | V2 Instance Balance | V2 Weight Balance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ibex | 18943 | 13843 | 8585 | 54.7% | 0.906281 | 0.958692 |
| riscv32i | 6422 | 3859 | 1791 | 72.1% | 0.970800 | 0.989585 |

### Interpretation

V1 shows that architecture semantics alone can reduce crossing, but it may produce weak balance. V2 is the stronger result because it preserves most of the crossing reduction while repairing balance.

## Connectivity-Only Baseline

| Design | Connectivity-Only Crossing | Full V2 Crossing | Effect of Architecture Terms |
| --- | ---: | ---: | --- |
| Ibex | 13842 | 8585 | Full V2 is lower. |
| riscv32i | 2766 | 1791 | Full V2 is lower. |

### Interpretation

This comparison is important because it asks whether the result is only a generic graph effect. On both benchmarks, full V2 improves over the connectivity-only baseline, suggesting that architecture-aware terms add useful information.

## Graph-Context V3 Results

| Design | V2 Crossing | V3 Context Crossing | V3 Instance Balance | V3 Weight Balance | Effect |
| --- | ---: | ---: | ---: | ---: | --- |
| Ibex | 8585 | 7410 | 0.903490 | 0.994449 | Lower crossing than V2. |
| riscv32i | 1791 | 1800 | 0.984434 | 0.999717 | Similar crossing with better balance. |

### Interpretation

V3 uses graph-neighborhood confidence to decide how strongly to trust architecture semantics. It improves Ibex and stabilizes riscv32i. This makes the method more defensible than a pure rule-based classifier, because semantic labels are checked against local netlist context before influencing partitioning.

## Ablation Evidence

The riscv32i ablation study shows how different objective terms affect the result.

| Case | Crossing Proxy | Instance Balance | Weight Balance | Top Classes |
| --- | ---: | ---: | ---: | --- |
| full_v2 | 1791 | 0.970800 | 0.989585 | control / datapath |
| no_arch_penalty | 1783 | 0.981008 | 0.982192 | control / control |
| no_balance_penalty | 2050 | 0.831737 | 0.822471 | control / datapath |
| connectivity_only | 2766 | 0.936213 | 0.999859 | control / datapath |

### Interpretation

The ablation is useful because it shows trade-offs:

- removing balance penalties can damage balance,
- removing architecture penalties can preserve crossing but weaken semantic separation,
- connectivity-only is weaker than full V2 on the main crossing metric,
- full V2 gives the best overall compromise among crossing, balance, and interpretability.

## Key Figures

| Figure | Path | Purpose |
| --- | --- | --- |
| ASA-RV3D method flow | `results/figures/summary/asa_rv3d_method_flow.svg` | Shows the full pipeline and where the innovation enters. |
| Two RISC-V benchmark summary | `results/figures/summary/two_riscv_benchmark_partition_summary.svg` | Shows generic, v1, and v2 crossing reductions. |
| Multi-metric summary | `results/figures/summary/two_riscv_multi_metric_summary.svg` | Shows crossing, balance, and architecture separation together. |
| riscv32i ablation summary | `results/figures/summary/riscv32i_v2_ablation_summary.svg` | Shows the effect of removing objective terms. |

## What the Current Evidence Supports

The current experiments support these claims:

1. Architecture semantics can improve early tier assignment for RISC-V gate-level designs.
2. A direct architecture split is not enough; balance-aware refinement is necessary.
3. Architecture-aware V2 reduces crossing proxy on both current benchmarks.
4. Connectivity-only refinement is not as strong as the full architecture-aware method.
5. Graph-context confidence can improve or stabilize architecture-guided partitioning.

## What the Current Evidence Does Not Yet Prove

The current experiments do not yet prove:

1. true TSV reduction after full 3D placement and routing,
2. generalization across many RISC-V cores,
3. superiority against mature academic or commercial partitioners,
4. timing, power, or thermal improvement after physical implementation.

These limitations should be stated clearly in reports and presentations. The strength of the project is not overclaiming; it is a reproducible, explainable, architecture-aware prototype with quantitative evidence.

## Recommended Next Experiments

The most valuable next steps are:

1. Add at least one more RISC-V benchmark if runtime allows.
2. Add random-seed or perturbation tests to show stability.
3. Extend connectivity-only and ablation results to both benchmarks.
4. Add physical-aware proxies such as estimated wirelength or locality.
5. Explore optional GNN-assisted scoring using the current graph-context scores as input features.

## Current Project Position

ASA-RV3D is best positioned as:

> a lightweight, explainable, reproducible RISC-V architecture-aware tier-partitioning framework, with graph-context confidence and balance-aware local refinement.

That is a credible project scope. It is not yet a complete 3D IC design system, but it is a strong foundation for one.
