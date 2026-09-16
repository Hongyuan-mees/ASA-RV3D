# RV3D-Public

Architecture-semantic-aware 2-tier partitioning prototype for RISC-V gate-level designs.

RV3D-Public explores whether RISC-V architectural semantics, scenario-specific 3D cost models, graph-context confidence, and lightweight physical-context evidence can improve early-stage tier assignment. Instead of treating a gate-level netlist as an anonymous graph, the project maps instances back to RISC-V architecture units and uses explainable local refinement to reduce inter-tier communication while preserving tier balance.

The project is a reproducible research prototype. It is not a complete 3D physical design tool and does not claim signoff timing, power, thermal, TSV, or hybrid-bonding results.

## Highlights

- Public experimental pipeline based on ORFS/OpenROAD sky130hd outputs.
- Two RISC-V benchmarks: Ibex and riscv32i.
- Clean baseline layouts with zero route DRC report lines.
- Gate-level architecture semantic classification and RISC-V unit mapping.
- Graph-context scoring that checks whether local netlist neighborhoods support semantic labels.
- Scenario-aware 3D proxy objectives for control/datapath split, memory-near-logic, and state/clock protection.
- Coverage-gated physical-context features from DEF placement, HPWL proxies, fanout, and observability diagnostics.
- Final guarded physical-context partitioner, `partition_v4b_physical_guarded.py`.

## Current Benchmarks

| Design | Platform | Instances | Route DRC Lines | Status |
| --- | --- | ---: | ---: | --- |
| Ibex | sky130hd | 15601 | 0 | clean baseline |
| riscv32i | sky130hd | 5737 | 0 | clean baseline |

## Main Method

The current mainline algorithm is the guarded physical-context partitioner:

```text
scenario-aware tier assignment
+ graph-context semantic confidence
+ coverage-gated physical context
+ guarded local refinement
```

The final guarded stage first builds a strong scenario-aware assignment. It then accepts physical-context moves only when they improve the physical-augmented objective without meaningfully damaging the original scenario objective or balance. This keeps the physical signal useful but prevents it from over-moving small designs.

The final objective used for evaluation is:

```text
scenario proxy cost
+ architecture preference penalty
+ balance penalties
+ physical_context_crossing_penalty
```

## Final V4B Guarded Results

The table compares the previous `scenario_aware` result with the final guarded physical-context result under the same physical-augmented objective. Negative deltas are improvements.

| Design | Scenario | Crossing Delta | Physical Penalty Delta | Objective Reduction vs Scenario-Aware | Guarded Instance Balance | Guarded Weight Balance |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Ibex | control/datapath split | -271 | -76.85 | 2.84% | 0.941630 | 0.989616 |
| Ibex | memory-near-logic | -139 | -36.21 | 1.33% | 0.947447 | 0.992481 |
| Ibex | state/clock protected | -92 | -26.74 | 0.79% | 0.900012 | 0.952499 |
| riscv32i | control/datapath split | 0 | 0.00 | 0.00% | 0.994784 | 0.945901 |
| riscv32i | memory-near-logic | 0 | 0.00 | 0.00% | 0.996867 | 0.947644 |
| riscv32i | state/clock protected | -4 | -1.44 | 0.15% | 0.999651 | 0.938297 |

Across all six design-scenario cases, guarded physical-context partitioning is never worse than the previous scenario-aware baseline under the physical-augmented objective. It improves Ibex in all scenarios, preserves riscv32i when physical moves are not useful, and makes a small improvement for riscv32i state/clock.

## Method Overview

The current flow has eight stages:

1. Run ORFS/OpenROAD baseline for a public RISC-V design.
2. Extract compact gate-level features from final Verilog and selected reports.
3. Classify instances into architecture-related groups.
4. Map instances to formal RISC-V architecture units.
5. Compute graph-context semantic confidence from netlist connectivity.
6. Extract coverage-gated physical-context scores from DEF placement and wire proxies.
7. Run scenario-aware and guarded physical-context tier partitioning.
8. Generate compact benchmark summaries and retained figures.

## Repository Layout

```text
classifier/      Architecture semantic classifier and mapper.
configs/         RISC-V architecture and 3D scenario configurations.
docs/            Method notes and experiment documentation.
evaluation/      Metric evaluation, diagnosis, and summary scripts.
partition/       Tier partitioning algorithms.
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

Run the final guarded physical-context partitioner:

```bash
python3 partition/partition_v4b_physical_guarded.py \
  --features-dir results/ibex_features \
  --scenario state_and_clock_protected \
  --guard-min-instance-balance 0.90 \
  --output-dir results/ibex_partition_v4b_physical_guard090/state_and_clock_protected
```

For riscv32i, replace `ibex` and `results/ibex_features` with `riscv32i` and `results/riscv32i_features`.

## Key Outputs

```text
results/benchmark_summary/v4b_guard090_summary.csv
results/benchmark_summary/v4_physical_comparison.csv
results/benchmark_summary/physical_coverage_summary.csv
results/benchmark_summary/physical_context_unit_ranking.csv
results/benchmark_summary/scenario_transfer_best_summary.csv
results/benchmark_summary/state_clock_diagnosis_summary.csv
docs/project-index.md
docs/asa-rv3d-method.md
docs/experiment-summary.md
```

## Limitations

- `crossing_connections_proxy` is a communication proxy, not a true TSV count.
- Physical context uses extracted placement and wire proxies; it is not full 3D placement/routing.
- The current physical term is coverage-gated because some architecture units have weak DEF observability.
- Architecture classification is rule-based with graph and physical confidence signals; it is not a trained GNN.
- Current evaluation covers two RISC-V designs; more benchmarks would strengthen the evidence.

## Roadmap

- Add more RISC-V benchmarks if runtime allows.
- Add random-seed or perturbation tests for stability.
- Improve architecture mapping for low-observability units such as register-file/state structures.
- Calibrate physical proxy weights against richer placement, timing, or wirelength data.
- Explore optional GNN-assisted scoring as a future module, using current graph/physical/context features as inputs.
