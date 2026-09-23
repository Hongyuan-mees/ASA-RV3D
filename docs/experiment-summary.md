# Experiment Summary

This document summarizes the current ASA-RV3D experimental evidence.

ASA-RV3D is an architecture-semantic-aware tier assignment prototype for RISC-V gate-level designs. The current strongest result uses TritonPart as a mature hypergraph partitioning backend and applies ASA-RV3D as a timing-aware architecture/scenario/physical repair layer.

## Benchmark Set

| Design | Source Flow | Platform | Instances | Baseline Status | Route DRC Lines |
| --- | --- | --- | ---: | --- | ---: |
| Ibex | ORFS/OpenROAD | sky130hd | 15601 | clean | 0 |
| riscv32i | ORFS/OpenROAD | sky130hd | 5737 | clean | 0 |

The repository stores compact CSV/JSON/SVG summaries. The current benchmark set covers Ibex, riscv32i, and PicoRV32 on sky130hd. Large ORFS physical artifacts such as DEF, GDS, ODB, SPEF, and full logs are kept outside Git.

## Compared Methods

| Name | Meaning |
| --- | --- |
| `TritonPart` | Strong 2-way hypergraph partition baseline. |
| `No timing guard` | ASA-RV3D ablation over TritonPart with architecture/scenario/physical repair but without timing-regret rejection. |
| `ASA-RV3D` | Complete method with OpenSTA-derived timing-regret rejection. |
| `scenario_aware`, `physical_guarded`, `v4b` | Internal/standalone ASA-RV3D ablations retained for development history and mechanism checks. |

## What Changed After Adding TritonPart

TritonPart is a strong raw-cut baseline. On both designs, it produces much lower crossing proxies than the standalone ASA-RV3D heuristic. This changes the project positioning:

```text
not:  ASA-RV3D beats TritonPart on raw cut
but:  ASA-RV3D adds architecture/scenario/physical repair on top of TritonPart
```

This is a stronger and more honest contribution. TritonPart supplies the mature connectivity partition. ASA-RV3D supplies RISC-V-aware interpretation, scenario-specific cost evaluation, physical-context scoring, and no-timing-guard ablation.

## Four-Core TritonPart + ASA-RV3D Main Result

The table compares TritonPart initial assignments against the current ASA-RV3D timing-regret guarded repair. `No timing guard` is only an ablation used in figures, not a separate final algorithm.

Across 12 design-scenario cases on four RISC-V cores, ASA-RV3D reduces timing-weighted crossings in every case. The reduction ranges from 0.72% to 12.09%, with a mean reduction of 7.30%.

| Design | Scenario | TritonPart timing risk | ASA-RV3D timing risk | Reduction vs TritonPart | ASA crossing nets | High-timing crossing nets |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| riscv32i | control/datapath split | 11.439 | 11.336 | 0.90% | 285 | 8 |
| riscv32i | memory-near-logic | 11.439 | 11.336 | 0.90% | 303 | 8 |
| riscv32i | state/clock protected | 11.439 | 11.357 | 0.72% | 292 | 8 |
| Ibex | control/datapath split | 19.145 | 17.842 | 6.81% | 258 | 5 |
| Ibex | memory-near-logic | 19.145 | 17.749 | 7.29% | 265 | 5 |
| Ibex | state/clock protected | 19.145 | 18.798 | 1.81% | 281 | 6 |
| PicoRV32 | control/datapath split | 24.723 | 21.963 | 11.16% | 353 | 8 |
| PicoRV32 | memory-near-logic | 24.723 | 22.032 | 10.88% | 381 | 8 |
| PicoRV32 | state/clock protected | 24.723 | 22.034 | 10.87% | 414 | 8 |
| SCR1 core tuned | control/datapath split | 15.962 | 14.032 | 12.09% | 285 | 6 |
| SCR1 core tuned | memory-near-logic | 15.962 | 14.032 | 12.09% | 286 | 6 |
| SCR1 core tuned | state/clock protected | 15.962 | 14.032 | 12.09% | 288 | 6 |

SCR1 uses a tuned 20 ns OpenROAD-flow-scripts configuration with closed setup/hold timing and zero route DRC. SERV is retained as a small boundary benchmark rather than part of this headline table.

Primary data file: `results/benchmark_summary/timing_regret_guarded_four_riscv_summary.csv`.

## Standalone ASA-RV3D Evidence

## Timing Guard Ablation

The repository keeps a `No timing guard` ablation. It uses the same TritonPart starting point and the same architecture/scenario/physical repair machinery as ASA-RV3D, but disables OpenSTA-derived timing-regret rejection.

This ablation is not the final algorithm. It is used to show that architecture/scenario/physical repair can improve a proxy objective while accidentally increasing timing-sensitive crossings. The current ASA-RV3D timing-regret flow adds this guard and is the result reported as the main algorithm.

Figure legend convention:

- `TritonPart`: strong hypergraph partition baseline.
- `No timing guard`: ASA-RV3D ablation without timing-regret rejection.
- `ASA-RV3D`: complete method.

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
6. Physical no-timing-guard ablation improves the TritonPart physical-augmented objective across the original six Ibex/riscv32i cases and supports the value of the physical-context layer.
7. Timing-regret no-timing-guard ablation reduces timing-weighted crossing relative to the previous no-timing-guard ablation in all nine tested design-scenario cases.

## What The Current Evidence Does Not Yet Prove

The current experiments do not yet prove:

1. true TSV reduction after full 3D placement and routing,
2. generalization across many RISC-V cores,
3. final timing-closure, power, or thermal improvement after physical implementation,
4. calibrated physical cost accuracy,
5. superiority over industrial or GNN-based 3D partitioning flows.

These limitations should be stated clearly. The strength of the project is not overclaiming; it is a reproducible, explainable prototype that now connects a mature partitioning backend with architecture semantics, graph evidence, scenario modeling, and physical-context repair.

## Recommended Next Experiments

The most valuable next steps are:

1. Add random-seed or perturbation tests for TritonPart and repair stability.
2. Add one more RISC-V benchmark if it can run the full flow cleanly, and probe a second strong partition backend such as Mt-KaHyPar/KaHyPar.
3. Improve mapping for low-observability units, especially register-file/state structures.
4. Calibrate physical proxy weights using richer placement, timing, or wirelength data.
5. Keep the four-core headline set stable unless a new benchmark runs the full flow cleanly.

## Current Project Position

ASA-RV3D is best positioned as:

> a lightweight, explainable, reproducible RISC-V architecture-aware repair layer over TritonPart, using graph-context confidence, scenario-specific 3D proxy objectives, coverage-gated physical context, and OpenSTA timing-regret guards.

That is a credible project scope. It is not a complete 3D IC design system, but it has moved beyond a simple architecture-label partitioning toy.

<!-- PSEUDO3D_REALIZATION:START -->
## Pseudo-3D Realization Evidence

The pseudo-3D stage converts ASA-RV3D tier assignments into early 3D stack artifacts and metrics. It preserves OpenROAD 2D placement coordinates, splits instances into tier0/tier1 views, and exports vertical interconnect candidates for crossing nets.

Pseudo-3D proxy result: ASA-RV3D improves the timing-weighted vertical proxy over TritonPart in all 12 tested cases. The minimum reduction is 1.32%, the mean reduction is 20.69%, and the maximum reduction is 35.26%.

The pseudo-layout export is deliberately bounded: it produces tier-level CSV/SVG artifacts and candidate vertical links, but it does not claim true 3D P&R, TSV-cell insertion, 3D routing, signoff STA, power, or thermal closure.
<!-- PSEUDO3D_REALIZATION:END -->

<!-- PATH_AWARE_DOWNSTREAM_START -->
## Independent Downstream Validation: Path-Aware Guard

The downstream validation experiment addresses the paper's Section 5.2 question: do proxy improvements translate into a more timing-relevant downstream metric?  The evaluator adds a fixed vertical-link delay to OpenSTA max paths whenever adjacent path instances are assigned to different tiers.

The original timing-regret ASA-RV3D result improves net-level timing-weighted crossing, but Ibex shows that this is not sufficient for path-level timing continuity: the ASA-RV3D assignment can fragment OpenSTA critical paths.  The path-aware extension therefore adds a guarded path-block repair stage that explicitly reduces critical-path tier transitions while preserving balance and bounding net-crossing growth.

Summary over 12 design-scenario cases:

- Mean critical-path crossing fraction: 61.8% before path-aware repair, 24.5% after path-aware repair.
- Mean WNS-degradation reduction versus ASA-RV3D: 25.0%.
- Mean TNS-degradation reduction versus ASA-RV3D: 32.7%.
- Ibex: fixed vertical-delay WNS/TNS degradation is removed in all three scenarios.
- riscv32i: TNS degradation improves by about 30.6%, while WNS degradation remains unchanged.
- PicoRV32 and SCR1 tuned are neutral in WNS/TNS because the fixed-delay proxy has no degradation left to remove.
- Trade-off: net-crossing proxy increases by 9.3% on average and 18.1% at worst, with guarded balance preserved.

These results should be presented as independent downstream proxy evidence, not as full 3D signoff timing closure.
<!-- PATH_AWARE_DOWNSTREAM_END -->

