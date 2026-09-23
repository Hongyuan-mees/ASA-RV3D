# RV3D-Public

RV3D-Public is a reproducible research prototype for architecture-aware early-stage 3D partitioning of RISC-V gate-level netlists.  The current main flow keeps TritonPart as the strong connectivity-first hypergraph baseline, then applies ASA-RV3D guarded repair using recovered RISC-V architecture semantics, physical context, OpenSTA-derived timing context, and path-aware downstream validation.

The repository is intended to support both RISC-V competition review and research reuse.  It is not a signoff 3D physical-design tool: the reported metrics are early-stage partitioning, timing-risk, and vertical-delay proxy metrics rather than TSV/hybrid-bonding signoff, full 3D routing, thermal closure, or final PPA claims.

## What This Repository Provides

- TritonPart-based 2-way hypergraph partitioning baselines for public RISC-V cores.
- ASA-RV3D timing-regret guarded repair over TritonPart assignments.
- RISC-V architecture semantic recovery for gate-level instances.
- OpenROAD/OpenSTA-derived physical and timing context.
- Path-aware downstream vertical-delay proxy validation.
- Multi-core benchmark results across Ibex, riscv32i, PicoRV32, and tuned SCR1, with SERV as a boundary/sanity case.
- Reproducible result summaries, figures, and navigation indices for competition review and research reuse.

## Main Result Snapshot

- Full ASA-RV3D timing-regret guarded repair reduces timing-weighted inter-tier crossing across the 12 primary design-scenario cases.
- Path-aware ASA-RV3D reduces the estimated downstream vertical-delay impact relative to the timing-regret ASA-RV3D assignment in the cases where OpenSTA path fragmentation is exposed.
- Component ablations show that timing-regret and path-aware guards optimize different risk views: net-level timing-sensitive crossings and path-level continuity.
- Robustness checks sweep vertical-link delay, OpenSTA path count, and path-aware repair budget.
- Scenario behavior analysis shows that scenario intent is visible but intentionally conservative under timing and balance guardrails.

## Quick Navigation

| Need | Start Here |
| --- | --- |
| Method overview | `docs/asa-rv3d-method.md` |
| Result map | `docs/result-index.md` |
| Reproduction guide | `docs/reproduction-guide.md` |
| Project file index | `docs/project-index.md` |
| Main figures | `results/figures/paper/` |
| Benchmark summaries | `results/benchmark_summary/` |
| Readiness audit | `results/benchmark_summary/paper_readiness_audit.md` |

## Main Method

```text
TritonPart 2-way hypergraph partition
+ ASA-RV3D architecture/scenario/physical evaluation
+ OpenSTA-derived timing-regret guard
= ASA-RV3D final tier assignment
```

TritonPart provides a strong connectivity-first cut. ASA-RV3D does not claim raw-cut superiority over TritonPart. Instead, it repairs the TritonPart assignment with small guarded local moves when those moves improve architecture/scenario/physical objectives without unacceptable timing-regret or balance degradation.

The final ASA-RV3D objective evaluates:

- scenario-specific 3D integration intent,
- RISC-V architecture-unit preference,
- graph-context confidence,
- coverage-gated physical-context crossing risk,
- OpenSTA-derived timing-context crossing risk,
- instance and architecture-weight balance.

`No timing guard` is an ablation of ASA-RV3D used only in figures to show why timing-regret rejection is necessary.

## Physical-Context Ablation: TritonPart + ASA-RV3D

This table is retained as a physical-context ablation. It compares TritonPart initial assignments against ASA-RV3D guarded repair before the later timing-regret and path-aware extensions became the main flow.

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

## SERV Boundary Benchmark

SERV is retained as a small serial RISC-V boundary benchmark. Unlike the four headline cores, TritonPart already produces a very small timing-crossing footprint on SERV. ASA-RV3D improves the guarded objective by 1.57% to 5.83% across the three scenarios while keeping timing-weighted crossing nearly unchanged, with at most 0.32% degradation. This result is used as a guardrail sanity check rather than as a headline improvement case.

## Timing Guard Ablation

The repository keeps a `No timing guard` ablation. It uses the same TritonPart starting point and the same architecture/scenario/physical repair machinery as ASA-RV3D, but disables OpenSTA-derived timing-regret rejection.

This ablation is not the final algorithm. It is used to show that architecture/scenario/physical repair can improve a proxy objective while accidentally increasing timing-sensitive crossings. The current ASA-RV3D timing-regret flow adds this guard and is the result reported as the main algorithm.

Figure legend convention:

- `TritonPart`: strong hypergraph partition baseline.
- `No timing guard`: ASA-RV3D ablation without timing-regret rejection.
- `ASA-RV3D`: complete method.

## Internal ASA-RV3D-Only Result

The repository also includes the standalone v4b guarded physical-context partitioner, `partition_v4b_physical_guarded.py`. This version starts from a scenario-aware assignment rather than from TritonPart. It is useful as an ablation showing that guarded physical-context refinement is beneficial even without a mature hypergraph backend.

## Method Overview

The current flow has nine stages:

1. Run ORFS/OpenROAD baseline for a public RISC-V design.
2. Extract compact gate-level features from final Verilog and selected reports.
3. Classify instances into architecture-related groups.
4. Map instances to formal RISC-V architecture units.
5. Compute graph-context semantic confidence from netlist connectivity.
6. Extract coverage-gated physical-context scores from DEF placement and wire proxies.
7. Export the netlist hypergraph to TritonPart and import its 2-way assignment.
8. Run ASA-RV3D guarded repair over the TritonPart assignment.
9. Generate compact benchmark summaries and retained figures.

## Repository Layout

<!-- PSEUDO3D_REALIZATION:START -->
## Pseudo-3D Realization

ASA-RV3D now includes a pseudo-3D realization stage. This is not true 3D place-and-route. It interprets each 2-tier assignment as an early 3D stack, then evaluates cross-tier vertical-link risk using architecture, timing, and physical context.

Across 12 design-scenario cases over `ibex,picorv32,riscv32i,scr1_core_tuned`, ASA-RV3D reduces the timing-weighted vertical proxy versus TritonPart in every case. The reduction range is 1.32% to 35.26%, with a mean of 20.69%.

The layout exporter also emits tier-level artifacts and vertical interconnect candidates. Across the current suite it exports 3691 candidate crossing nets and 6674 vertical connection proxy endpoints.

| Design | Scenario | Top candidate net | Timing-risk vertical proxy |
| --- | --- | --- | ---: |
| picorv32 | control_datapath_split | net330 | 5.707 |
| picorv32 | memory_near_logic | net330 | 5.660 |
| picorv32 | state_and_clock_protected | net330 | 5.498 |
| scr1_core_tuned | control_datapath_split | clknet_0_clk_pipe | 3.854 |

These outputs are intended for reproducible 3D-aware validation and presentation, not signoff TSV insertion, 3D routing, parasitic extraction, or thermal analysis.
<!-- PSEUDO3D_REALIZATION:END -->

```text
classifier/      Architecture semantic classifier and mapper.
configs/         RISC-V architecture and 3D scenario configurations.
docs/            Method notes and experiment documentation.
evaluation/      Metric evaluation, diagnosis, and summary scripts.
partition/       Tier partitioning and repair algorithms.
results/         Lightweight CSV/JSON/SVG results committed to Git.
scripts/         Feature extraction and utility scripts.
third_party/     Reserved for external references if needed.
```

Large ORFS physical artifacts such as DEF, ODB, GDS, SPEF, and full logs are not copied into this repository. The repository stores compact, reproducible summaries instead.

## Reproduce

The fastest retained entry point is:

```bash
bash scripts/reproduce_core_results.sh
```

The full flow has three layers:

1. Run ORFS/OpenROAD for each design to produce `6_final.v`, `6_final.def`, `6_final.odb`, `6_final.sdc`, and `6_final.spef`.
2. Extract ASA-RV3D features: architecture mapping, graph context, coverage-gated physical context, and OpenSTA timing context.
3. Export a TritonPart hypergraph, import its 2-way assignment, and run the current ASA-RV3D timing-regret flow.

Example for one scenario after features and TritonPart assignment exist:

```bash
python3 partition/partition_tritonpart_timing_regret_guarded_repair.py \
  --design ibex \
  --scenario state_and_clock_protected \
  --features-dir results/ibex_features \
  --tritonpart-assignment results/ibex_tritonpart_baseline/tritonpart_assignment.csv \
  --output-dir results/ibex_tritonpart_timing_regret_guarded_repair/state_and_clock_protected
```

## Key Outputs

```text
results/benchmark_summary/timing_regret_guarded_four_riscv_summary.csv
results/benchmark_summary/scr1_core_tuned_timing_regret_guarded_summary.csv
results/benchmark_summary/serv_timing_regret_guarded_summary.csv
results/benchmark_summary/physical_coverage_summary.csv
results/figures/final/*timing_weighted_crossing.svg
results/figures/summary/asa_rv3d_method_flow.svg
```

## Limitations

- ASA-RV3D is a partitioning and feasibility-analysis prototype, not a complete 3D physical design tool.
- `crossing_connections_proxy` and timing-weighted crossing are communication/risk proxies, not signoff TSV, hybrid-bonding, thermal, power, or IR-drop metrics.
- Physical context uses DEF placement, fanout, HPWL, and observability proxies; it is not full 3D placement and routing.
- SCR1 uses a tuned 20 ns ORFS configuration. This is documented because the quick 10 ns configuration did not close timing.
- SERV is retained as a small boundary benchmark, not as a headline improvement case.
- Architecture classification is rule-based with graph, physical, and timing confidence signals; it is not a trained GNN.

## Roadmap

- Add pseudo-3D feasibility validation: per-tier balance, cross-tier channel pressure, timing-sensitive TSV pressure, and physical-risk TSV pressure.
- Keep the four-core headline table as the main benchmark set unless a new design can run cleanly through the full ORFS and ASA-RV3D flow.
- Improve the reproducibility entry point so one script can regenerate retained headline CSVs and figures.
- Optionally compare against a second strong partition backend such as Mt-KaHyPar/KaHyPar after the pseudo-3D layer is in place.

<!-- PATH_AWARE_DOWNSTREAM_START -->
## Path-Aware Downstream Validation

The current downstream validation is a path-level proxy rather than signoff 3D STA.  It injects a fixed vertical-link delay on OpenSTA max paths and compares three assignments: TritonPart, ASA-RV3D timing-regret guarded repair, and path-aware ASA-RV3D.

Across 12 design-scenario cases (riscv32i,ibex,picorv32,scr1_core_tuned), path-aware ASA-RV3D reduces the mean critical-path crossing fraction from 61.8% to 24.5%.  It improves WNS-degradation proxy in 3/12 cases and TNS-degradation proxy in 6/12 cases; neutral cases generally had no measurable downstream degradation to remove.

- Ibex: path-aware repair removes the fixed vertical-delay WNS/TNS degradation in all three scenarios.
- riscv32i: WNS degradation is unchanged, while TNS degradation improves by about 30.6% in all three scenarios.
- PicoRV32: crossing-path fraction is eliminated, but WNS/TNS degradation was already zero, so QoR is neutral.
- SCR1 tuned: top critical paths were already single-tier under this proxy, making it a boundary neutral case.

This downstream gain has a controlled cost: net-crossing proxy increases by 9.3% on average and at most 18.1%, while balance remains guarded (`min instance balance = 0.9036`, `min weight balance = 0.9042`).  The intended interpretation is not that ASA-RV3D minimizes raw crossing, but that it can selectively trade limited additional inter-tier communication for lower critical-path vertical-delay exposure.
<!-- PATH_AWARE_DOWNSTREAM_END -->

