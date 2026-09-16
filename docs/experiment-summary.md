# Experiment Summary

This document summarizes the current ASA-RV3D experimental evidence.

ASA-RV3D is an architecture-semantic-aware tier partitioning prototype for RISC-V gate-level designs. The current evaluation asks whether architecture semantics, graph-context confidence, 3D scenario objectives, and coverage-gated physical context can reduce inter-tier crossing proxies while preserving usable tier balance.

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
| `architecture_score_v2` | Balance-aware local refinement with architecture penalty. |
| `v3_context` | Graph-context version that scales architecture guidance by semantic confidence. |
| `scenario_aware` | Scenario-specific objective using 3D integration cost models. |
| `physical_context_aware` | Unguarded v4 physical-context objective variant. |
| `physical_guarded` | Final v4b method: scenario-aware assignment plus guarded physical-context refinement. |

## V2 And V3 Evidence

Lower `crossing_connections_proxy` is better.

| Design | Generic Crossing | V2 Crossing | V3 Context Crossing | V3 Instance Balance | V3 Weight Balance |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ibex | 18943 | 8585 | 7410 | 0.903490 | 0.994449 |
| riscv32i | 6422 | 1791 | 1800 | 0.984434 | 0.999717 |

### Interpretation

V2 shows that architecture-aware refinement can reduce crossing while preserving usable balance. V3 adds graph-context confidence, which improves Ibex and stabilizes riscv32i. This makes the method more defensible than pure rule-based classification because semantic labels are checked against local netlist context before influencing partitioning.

## Scenario-Aware Evidence

Scenario-aware partitioning evaluates different 3D integration assumptions, including:

- control/datapath split,
- memory-near-logic,
- state/clock protected.

Scenario transfer tests show that scenario-aware assignments consistently improve over generic and v3_context baselines under scenario-specific proxy objectives. The non-own-best cases are explainable and mostly dominated by flexible generated control/datapath logic rather than large-scale movement of critical architecture units.

## Physical-Context Evidence

Physical-context scoring adds lightweight placement and wire proxies:

- DEF component matching,
- placement region,
- net HPWL proxy,
- fanout exposure,
- clock/reset exposure,
- unit-level physical observability.

The key safeguard is coverage gating. Units with poor DEF observability, such as some register-file/state structures, receive low physical confidence so missing coordinates do not create false physical evidence.

## Final V4B Guard090 Results

The current final candidate is `partition_v4b_physical_guarded.py` with:

```text
--guard-min-instance-balance 0.90
```

The table compares `physical_guarded` with the previous `scenario_aware` baseline under the same physical-augmented objective.

| Design | Scenario | Crossing Delta | Physical Penalty Delta | Objective Reduction vs Scenario-Aware | Guarded Instance Balance | Guarded Weight Balance | Improves Baseline |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ibex | control/datapath split | -271 | -76.85 | 2.84% | 0.941630 | 0.989616 | 1 |
| Ibex | memory-near-logic | -139 | -36.21 | 1.33% | 0.947447 | 0.992481 | 1 |
| Ibex | state/clock protected | -92 | -26.74 | 0.79% | 0.900012 | 0.952499 | 1 |
| riscv32i | control/datapath split | 0 | 0.00 | 0.00% | 0.994784 | 0.945901 | 1 |
| riscv32i | memory-near-logic | 0 | 0.00 | 0.00% | 0.996867 | 0.947644 | 1 |
| riscv32i | state/clock protected | -4 | -1.44 | 0.15% | 0.999651 | 0.938297 | 1 |

### Interpretation

The guarded physical-context stage behaves as intended:

- It improves all three Ibex scenarios.
- It preserves riscv32i assignments when physical moves do not help.
- It makes a small improvement for riscv32i state/clock.
- It does not worsen the previous scenario-aware baseline in any tested design-scenario case.
- The 0.90 instance-balance guard prevents the physical term from over-moving large scenarios.

This is stronger than the unguarded v4 result because it shows discipline: the physical term is allowed to help, but not allowed to damage a strong scenario-aware solution.

## What The Current Evidence Supports

The current experiments support these claims:

1. Architecture semantics can improve early tier assignment for RISC-V gate-level designs.
2. Direct architecture splitting is not enough; balance-aware refinement is necessary.
3. Graph-context confidence improves or stabilizes architecture-guided partitioning.
4. Scenario-specific 3D proxy objectives reveal meaningful partition behavior.
5. Coverage-gated physical-context refinement can improve scenario-aware assignments without sacrificing balance.
6. Guarded refinement is safer than unguarded physical weighting, especially for smaller designs.

## What The Current Evidence Does Not Yet Prove

The current experiments do not yet prove:

1. true TSV reduction after full 3D placement and routing,
2. generalization across many RISC-V cores,
3. superiority against mature academic or commercial partitioners,
4. timing, power, or thermal improvement after physical implementation,
5. calibrated physical cost accuracy.

These limitations should be stated clearly. The strength of the project is not overclaiming; it is a reproducible, explainable prototype that now connects architecture semantics, graph evidence, scenario modeling, and physical-context proxies.

## Recommended Next Experiments

The most valuable next steps are:

1. Add at least one more RISC-V benchmark if runtime allows.
2. Add random-seed or perturbation tests to show stability.
3. Improve mapping for low-observability units, especially register-file/state structures.
4. Calibrate physical proxy weights using richer placement, timing, or wirelength data.
5. Explore optional GNN-assisted scoring using current graph-context and physical-context scores as input features.

## Current Project Position

ASA-RV3D is best positioned as:

> a lightweight, explainable, reproducible RISC-V architecture-aware tier-partitioning framework, with graph-context confidence, scenario-specific 3D proxy objectives, and guarded physical-context refinement.

That is a credible project scope. It is not a complete 3D IC design system, but it now has a clearer technical arc than a simple architecture-label partitioning toy.
