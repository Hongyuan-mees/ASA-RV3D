# Experiment Summary

This document summarizes the current ASA-RV3D experimental evidence.

ASA-RV3D is an architecture-semantic-aware tier assignment prototype for RISC-V gate-level designs. The current strongest result uses TritonPart as a mature hypergraph partitioning backend and applies ASA-RV3D as a guarded architecture/scenario/physical/timing repair layer.

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
| `architecture_score_v2` | Balance-aware local refinement with architecture penalty. |
| `v3_context` | Graph-context version that scales architecture guidance by semantic confidence. |
| `scenario_aware` | Scenario-specific objective using 3D integration cost models. |
| `physical_guarded` | Standalone v4b method: scenario-aware assignment plus guarded physical-context refinement. |
| `tritonpart_initial` | TritonPart 2-way hypergraph partition baseline. |
| `tritonpart_guarded_repair` | ASA-RV3D guarded repair over the TritonPart assignment. |
| `timing_regret_guarded_repair` | OpenSTA-derived timing-regret guard over TritonPart repair. |

## What Changed After Adding TritonPart

TritonPart is a strong raw-cut baseline. On both designs, it produces much lower crossing proxies than the standalone ASA-RV3D heuristic. This changes the project positioning:

```text
not:  ASA-RV3D beats TritonPart on raw cut
but:  ASA-RV3D adds architecture/scenario/physical repair on top of TritonPart
```

This is a stronger and more honest contribution. TritonPart supplies the mature connectivity partition. ASA-RV3D supplies RISC-V-aware interpretation, scenario-specific cost evaluation, physical-context scoring, and guarded repair.

## TritonPart + ASA-RV3D Guarded Repair

The table compares TritonPart initial assignments against ASA-RV3D guarded repair under the same physical-augmented objective.

| Design | Scenario | Crossing Delta | Objective Reduction vs TritonPart | Repaired Instance Balance | Repaired Weight Balance |
| --- | --- | ---: | ---: | ---: | ---: |
| Ibex | control/datapath split | -21 | 5.55% | 0.917999 | 0.932054 |
| Ibex | memory-near-logic | -16 | 6.21% | 0.919651 | 0.933904 |
| Ibex | state/clock protected | +19 | 9.48% | 0.917999 | 0.932604 |
| riscv32i | control/datapath split | +3 | 3.44% | 0.933603 | 0.900383 |
| riscv32i | memory-near-logic | +23 | 4.13% | 0.931000 | 0.900383 |
| riscv32i | state/clock protected | +19 | 3.95% | 0.933603 | 0.900383 |

### Interpretation

The repair layer improves the physical-augmented objective in all six design-scenario cases:

- Ibex improves by `5.6%` to `9.5%`.
- riscv32i improves by `3.4%` to `4.1%`.
- Crossing proxy sometimes increases slightly, but remains very low because TritonPart already provides a strong cut.
- The increase is acceptable because the repair optimizes a broader architecture/scenario/physical objective rather than pure cut count.
- Balance guardrails remain active: repaired weight balance is at least `0.900383`.

This supports the revised main claim:

> ASA-RV3D is useful as an explainable architecture/scenario/physical repair layer over a mature hypergraph partitioner.

### Seed Robustness

A five-seed TritonPart robustness check was run on riscv32i `state_and_clock_protected`. ASA-RV3D guarded repair improved the physical-augmented objective for all five seeds.

| Seed | Initial Crossing | Repaired Crossing | Objective Reduction | Repaired Instance Balance | Repaired Weight Balance |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 731 | 750 | 3.95% | 0.933603 | 0.900383 |
| 1 | 730 | 750 | 3.59% | 0.934255 | 0.900000 |
| 2 | 733 | 756 | 3.95% | 0.933603 | 0.900383 |
| 3 | 645 | 643 | 3.88% | 0.928403 | 0.894271 |
| 4 | 639 | 638 | 3.54% | 0.925814 | 0.896559 |

For seeds 3 and 4, the TritonPart initial weight balance is already below 0.90. The adaptive guard therefore preserves the initial balance level rather than forcing an unrealistic fixed threshold.
## Standalone ASA-RV3D Evidence

## Timing-Regret Guarded Repair

A timing diagnostic was added after the TritonPart guarded repair experiments. The diagnostic showed that the physical/scenario repair can improve the physical-augmented objective while increasing timing-critical crossing risk. This is a real weakness, not a cosmetic issue.

The new timing-regret guarded repair uses OpenSTA `report_checks` paths to build instance-level timing context scores. During local repair, moves that increase timing risk beyond a small regret budget are rejected.

| Design | Scenario | TritonPart | Guarded Repair | Timing-Regret Guarded | Reduction vs Guarded | Reduction vs TritonPart |
| ------ | -------- | ---------: | -------------: | --------------------: | -------------------: | ----------------------: |
| riscv32i | control/datapath | 11.439099 | 11.747528 | 11.336352 | 3.50% | 0.90% |
| riscv32i | memory-near-logic | 11.439099 | 11.462790 | 11.336352 | 1.10% | 0.90% |
| riscv32i | state/clock protected | 11.439099 | 12.377965 | 11.356957 | 8.25% | 0.72% |
| Ibex | control/datapath | 19.145480 | 20.285616 | 17.841802 | 12.05% | 6.81% |
| Ibex | memory-near-logic | 19.145480 | 21.487844 | 17.749418 | 17.40% | 7.29% |
| Ibex | state/clock protected | 19.145480 | 24.139121 | 18.798488 | 22.12% | 1.81% |

This is the strongest current evidence that ASA-RV3D adds value beyond pure connectivity partitioning: it can repair a strong TritonPart partition using architecture, scenario, physical, and timing signals while preserving explicit balance guardrails.

The project also contains a standalone v4b guarded physical-context partitioner. It starts from a scenario-aware assignment rather than from TritonPart.

| Design | Scenario | Crossing Delta vs Scenario-Aware | Objective Reduction vs Scenario-Aware | Guarded Instance Balance | Guarded Weight Balance |
| --- | --- | ---: | ---: | ---: | ---: |
| Ibex | control/datapath split | -271 | 2.84% | 0.941630 | 0.989616 |
| Ibex | memory-near-logic | -139 | 1.33% | 0.947447 | 0.992481 |
| Ibex | state/clock protected | -92 | 0.79% | 0.900012 | 0.952499 |
| riscv32i | control/datapath split | 0 | 0.00% | 0.994784 | 0.945901 |
| riscv32i | memory-near-logic | 0 | 0.00% | 0.996867 | 0.947644 |
| riscv32i | state/clock protected | -4 | 0.15% | 0.999651 | 0.938297 |

This standalone result is still useful as an ablation. It shows that guarded physical-context refinement behaves sensibly even without TritonPart. But the TritonPart-backed flow is the stronger mainline.

## Earlier V2/V3 Evidence

Lower `crossing_connections_proxy` is better.

| Design | Generic Crossing | V2 Crossing | V3 Context Crossing | V3 Instance Balance | V3 Weight Balance |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ibex | 18943 | 8585 | 7410 | 0.903490 | 0.994449 |
| riscv32i | 6422 | 1791 | 1800 | 0.984434 | 0.999717 |

### Interpretation

V2 shows that architecture-aware refinement can reduce crossing while preserving usable balance. V3 adds graph-context confidence, which improves Ibex and stabilizes riscv32i. These stages are stepping stones toward the final TritonPart-backed repair layer.

## Physical-Context Evidence

Physical-context scoring adds lightweight placement and wire proxies:

- DEF component matching,
- placement region,
- net HPWL proxy,
- fanout exposure,
- clock/reset exposure,
- unit-level physical observability.

The key safeguard is coverage gating. Units with poor DEF observability, such as some register-file/state structures, receive low physical confidence so missing coordinates do not create false physical evidence.

## What The Current Evidence Supports

The current experiments support these claims:

1. Architecture semantics are useful for interpreting and repairing tier assignments.
2. Graph-context confidence improves or stabilizes architecture-guided partitioning.
3. Scenario-specific 3D proxy objectives reveal meaningful partition behavior.
4. Coverage-gated physical-context refinement can improve scenario-aware assignments without sacrificing balance.
5. TritonPart is a strong raw-cut backend.
6. ASA-RV3D guarded repair improves the TritonPart physical-augmented objective across all tested design-scenario cases.
7. Timing-regret guarded repair reduces timing-weighted crossing relative to the previous guarded repair in all tested design-scenario cases.

## What The Current Evidence Does Not Yet Prove

The current experiments do not yet prove:

1. true TSV reduction after full 3D placement and routing,
2. generalization across many RISC-V cores,
3. signoff timing closure, power, or thermal improvement after physical implementation,
4. calibrated physical cost accuracy,
5. superiority over industrial or GNN-based 3D partitioning flows.

These limitations should be stated clearly. The strength of the project is not overclaiming; it is a reproducible, explainable prototype that now connects a mature partitioning backend with architecture semantics, graph evidence, scenario modeling, and physical-context repair.

## Recommended Next Experiments

The most valuable next steps are:

1. Add random-seed or perturbation tests for TritonPart and repair stability.
2. Extend timing-regret guarded repair across all scenarios and additional seeds.
3. Improve mapping for low-observability units, especially register-file/state structures.
4. Calibrate physical proxy weights using richer placement, timing, or wirelength data.
5. Add more RISC-V benchmarks if runtime allows.

## Current Project Position

ASA-RV3D is best positioned as:

> a lightweight, explainable, reproducible RISC-V architecture-aware repair layer over TritonPart, using graph-context confidence, scenario-specific 3D proxy objectives, coverage-gated physical context, and OpenSTA timing-regret guards.

That is a credible project scope. It is not a complete 3D IC design system, but it has moved beyond a simple architecture-label partitioning toy.
