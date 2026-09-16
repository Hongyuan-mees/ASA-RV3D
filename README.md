# RV3D-Public

Architecture-semantic-aware 2-tier partitioning prototype for RISC-V gate-level designs.

RV3D-Public explores how RISC-V architectural semantics, 3D scenario cost models, graph-context confidence, lightweight physical-context evidence, and OpenSTA timing criticality can guide early-stage tier assignment. The current strongest flow uses TritonPart as a mature hypergraph partitioning backend, then applies ASA-RV3D as an explainable architecture/scenario/physical guarded repair layer.

The project is a reproducible research prototype. It is not a complete 3D physical design tool and does not claim signoff timing, power, thermal, TSV, or hybrid-bonding results.

## Highlights

- Public experimental pipeline based on ORFS/OpenROAD sky130hd outputs.
- Two RISC-V benchmarks: Ibex and riscv32i.
- Clean baseline layouts with zero route DRC report lines.
- Gate-level architecture semantic classification and RISC-V unit mapping.
- Graph-context scoring that checks whether local netlist neighborhoods support semantic labels.
- Scenario-aware 3D proxy objectives for control/datapath split, memory-near-logic, and state/clock protection.
- Coverage-gated physical-context features from DEF placement, HPWL proxies, fanout, and observability diagnostics.
- TritonPart baseline/backend integration.
- ASA-RV3D guarded repair over TritonPart assignments.
- Timing-regret guarded repair that prevents scenario/physical refinement from increasing timing-critical crossings.

## Current Benchmarks

| Design | Platform | Instances | Route DRC Lines | Status |
| --- | --- | ---: | ---: | --- |
| Ibex | sky130hd | 15601 | 0 | clean baseline |
| riscv32i | sky130hd | 5737 | 0 | clean baseline |

## Main Method

The current mainline is:

```text
TritonPart 2-way hypergraph partition
+ ASA-RV3D architecture/scenario/physical evaluation
+ guarded local repair
```

TritonPart provides a strong connectivity-first cut. ASA-RV3D does not try to beat TritonPart on raw cut count. Instead, it uses RISC-V architecture semantics, scenario-specific 3D costs, graph confidence, and physical-context risk to repair the TritonPart assignment when a small guarded move improves the physical-augmented objective.

The final repair objective evaluates:

```text
scenario proxy cost
+ architecture preference penalty
+ balance penalties
+ physical_context_crossing_penalty
+ timing_context_crossing_penalty in the timing-regret variant
```

The guardrails prevent repair from over-moving a strong hypergraph solution.

## Main Result: TritonPart + ASA-RV3D Guarded Repair

The table compares TritonPart initial assignments against ASA-RV3D guarded repair. Negative objective deltas are improvements.

| Design | Scenario | Crossing Delta | Objective Reduction vs TritonPart | Repaired Instance Balance | Repaired Weight Balance |
| --- | --- | ---: | ---: | ---: | ---: |
| Ibex | control/datapath split | -21 | 5.55% | 0.917999 | 0.932054 |
| Ibex | memory-near-logic | -16 | 6.21% | 0.919651 | 0.933904 |
| Ibex | state/clock protected | +19 | 9.48% | 0.917999 | 0.932604 |
| riscv32i | control/datapath split | +3 | 3.44% | 0.933603 | 0.900383 |
| riscv32i | memory-near-logic | +23 | 4.13% | 0.931000 | 0.900383 |
| riscv32i | state/clock protected | +19 | 3.95% | 0.933603 | 0.900383 |

Across all six design-scenario cases, ASA-RV3D guarded repair improves the TritonPart physical-augmented objective. Raw crossing can slightly increase because the repair is optimizing architecture/scenario/physical cost rather than pure cut count. The final crossing proxies remain very low because TritonPart supplies the strong initial partition.

### Adaptive Guard And Seed Robustness

The TritonPart repair guard is adaptive. If the TritonPart initial assignment already satisfies the requested balance floor, ASA-RV3D enforces that floor during repair. If the initial assignment is below the requested floor, ASA-RV3D prevents further balance degradation instead of forcing an unrealistic correction.

A five-seed robustness check on riscv32i `state_and_clock_protected` shows that guarded repair improves the TritonPart physical-augmented objective for all tested seeds. The objective reduction ranges from 3.54% to 3.95%.

## Timing-Regret Guarded Repair

The original TritonPart guarded repair improves the architecture/scenario/physical objective, but timing diagnostics showed that it can increase timing-critical crossings. RV3D-Public therefore adds an OpenSTA-derived timing context and a timing-regret guard.

The timing-regret variant rejects local moves that increase timing risk beyond a small per-move budget. Across two RISC-V designs and three 3D scenarios, it reduces timing-weighted crossing relative to the previous guarded repair in all six cases. It is also slightly better than the TritonPart initial assignment in all six cases.

| Design | Scenario | Reduction vs Guarded | Reduction vs TritonPart |
| ------ | -------- | -------------------: | ----------------------: |
| riscv32i | control/datapath | 3.50% | 0.90% |
| riscv32i | memory-near-logic | 1.10% | 0.90% |
| riscv32i | state/clock protected | 8.25% | 0.72% |
| Ibex | control/datapath | 12.05% | 6.81% |
| Ibex | memory-near-logic | 17.40% | 7.29% |
| Ibex | state/clock protected | 22.12% | 1.81% |

This result strengthens the project claim: ASA-RV3D is not only a scenario/physical repair layer, but can also use timing criticality to avoid repairing a partition in a timing-hostile direction.

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

Run the ORFS/OpenROAD baseline outside this repository, then extract features:

```bash
python3 scripts/extract_orfs_baseline.py \
  --orfs-flow-dir ~/openroad-flow-scripts/flow \
  --design ibex \
  --output-dir results/ibex_features
```

Classify and map architecture semantics:

```bash
python3 classifier/architecture_classifier.py \
  --features-dir results/ibex_features

python3 classifier/architecture_mapper.py \
  --features-dir results/ibex_features
```

Compute graph-context and physical-context scores:

```bash
python3 evaluation/graph_context_score.py \
  --features-dir results/ibex_features

python3 evaluation/physical_context_score.py \
  --design ibex \
  --features-dir results/ibex_features
```

Export a TritonPart hypergraph and import the partition:

```bash
python3 evaluation/export_tritonpart_hgr.py --design ibex

# Run results/ibex_tritonpart_baseline/run_tritonpart.tcl inside the ORFS/OpenROAD container,
# then copy ibex.hgr.part.2 back to results/ibex_tritonpart_baseline/.

python3 evaluation/import_tritonpart_partition.py --design ibex
```

Run ASA-RV3D guarded repair over the TritonPart assignment:

```bash
python3 partition/partition_tritonpart_guarded_repair.py \
  --design ibex \
  --scenario state_and_clock_protected \
  --output-dir results/ibex_tritonpart_guarded_repair/state_and_clock_protected
```

For riscv32i, replace `ibex` and `results/ibex_features` with `riscv32i` and `results/riscv32i_features`.

## Key Outputs

```text
results/benchmark_summary/tritonpart_guarded_repair_summary.csv
results/benchmark_summary/tritonpart_scenario_cost/
results/benchmark_summary/v4b_guard090_summary.csv
results/benchmark_summary/physical_coverage_summary.csv
results/benchmark_summary/physical_context_unit_ranking.csv
docs/project-index.md
docs/asa-rv3d-method.md
docs/experiment-summary.md
```

## Limitations

- `crossing_connections_proxy` is a communication proxy, not a true TSV count.
- Physical context uses extracted placement and wire proxies; it is not full 3D placement/routing.
- TritonPart is used as a strong backend; ASA-RV3D is a repair/evaluation layer, not a replacement for mature partitioners.
- The current physical term is coverage-gated because some architecture units have weak DEF observability.
- Architecture classification is rule-based with graph and physical confidence signals; it is not a trained GNN.
- Current evaluation covers two RISC-V designs; more benchmarks would strengthen the evidence.

## Roadmap

- Add more RISC-V benchmarks if runtime allows.
- Add random-seed or perturbation tests for TritonPart and guarded repair.
- Improve architecture mapping for low-observability units such as register-file/state structures.
- Calibrate physical proxy weights against richer placement, timing, or wirelength data.
- Extend timing-regret guarded repair across all scenarios and additional seeds.
- Explore optional GNN-assisted scoring as a future module, using current graph/physical/context features as inputs.
