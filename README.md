# RV3D-Public

Architecture-semantic-aware 2-tier partitioning prototype for RISC-V gate-level designs.

RV3D-Public explores how RISC-V architectural semantics, 3D scenario cost models, graph-context confidence, lightweight physical-context evidence, and OpenSTA timing criticality can guide early-stage tier assignment. The current strongest flow uses TritonPart as a mature hypergraph partitioning backend, then applies ASA-RV3D as an explainable architecture/scenario/physical/timing repair layer.

The project is a reproducible research prototype. It is not a complete 3D physical design tool and does not claim signoff timing, power, thermal, TSV, or hybrid-bonding results.

## Highlights

- Public experimental pipeline based on ORFS/OpenROAD sky130hd outputs.
- Four headline RISC-V benchmarks: riscv32i, Ibex, PicoRV32, and SCR1 core tuned.
- SERV is included as a small serial RISC-V boundary benchmark.
- Clean baseline layouts with zero route DRC report lines.
- Gate-level architecture semantic classification and RISC-V unit mapping.
- Graph-context scoring that checks whether local netlist neighborhoods support semantic labels.
- Scenario-aware 3D proxy objectives for control/datapath split, memory-near-logic, and state/clock protection.
- Coverage-gated physical-context features from DEF placement, HPWL proxies, fanout, and observability diagnostics.
- TritonPart baseline/backend integration.
- ASA-RV3D timing-aware repair over TritonPart assignments.
- A `No timing guard` ablation used only to show why timing-regret rejection is necessary.

## Current Benchmarks

| Design | Platform | Instances | Route DRC Lines | Status |
| --- | --- | ---: | ---: | --- |
| Ibex | sky130hd | 15601 | 0 | clean baseline |
| riscv32i | sky130hd | 5737 | 0 | clean baseline |

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

## Main Result: TritonPart + ASA-RV3D

The table compares TritonPart initial assignments against the complete ASA-RV3D method. `No timing guard` is only an ablation used in figures, not a separate final algorithm.

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

This ablation is not the final algorithm. It is used to show that architecture/scenario/physical repair can improve a proxy objective while accidentally increasing timing-sensitive crossings. The complete ASA-RV3D method adds the timing-regret guard and is the result reported as the main algorithm.

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
3. Export a TritonPart hypergraph, import its 2-way assignment, and run complete ASA-RV3D.

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

