# RV3D-Public

Architecture-semantic-aware 2-tier partitioning prototype for RISC-V gate-level designs.

RV3D-Public explores whether RISC-V architectural semantics can improve early-stage 3D IC tier assignment. Instead of treating a gate-level netlist as an anonymous graph, the project extracts lightweight structural features, recovers architecture-related instance groups, evaluates graph-neighborhood semantic confidence, and applies balance-aware local refinement to reduce inter-tier crossing connections.

The project is a reproducible research prototype. It is not a complete 3D physical design tool.

## Highlights

- Public, reproducible experimental pipeline based on ORFS/OpenROAD outputs.
- Two RISC-V benchmarks: Ibex and riscv32i.
- Clean sky130hd baselines with zero route DRC report lines.
- Rule-based architecture semantic classification for gate-level instances.
- Graph-context scoring that measures whether an instance's netlist neighborhood supports its semantic label.
- ASA-RV3D partitioning with crossing, balance, and architecture-semantics terms.
- Benchmark summaries, ablation studies, and SVG visualizations.

## Current Benchmarks

| Design | Platform | Instances | Route DRC Lines | Status |
| --- | --- | ---: | ---: | --- |
| Ibex | sky130hd | 15601 | 0 | clean baseline |
| riscv32i | sky130hd | 5737 | 0 | clean baseline |

## Main Results

The main metric is `crossing_connections_proxy`, a lightweight proxy for inter-tier communication. Lower is better.

| Design | Method | Crossing Proxy | Reduction vs Generic | Instance Balance | Weight Balance |
| --- | --- | ---: | ---: | ---: | ---: |
| Ibex | Generic balance | 18943 | 0.0% | 0.999872 | 0.999946 |
| Ibex | Architecture-aware v1 | 13843 | 26.9% | 0.821483 | 0.999946 |
| Ibex | Architecture-score v2 | 8585 | 54.7% | 0.906281 | 0.958692 |
| riscv32i | Generic balance | 6422 | 0.0% | 0.999651 | 0.999859 |
| riscv32i | Architecture-aware v1 | 3859 | 39.9% | 0.543449 | 0.613791 |
| riscv32i | Architecture-score v2 | 1791 | 72.1% | 0.970800 | 0.989585 |

## Graph-Context Enhancement

The project also includes an experimental graph-context partitioner, `partition_v3_context.py`.

Graph-context scoring does not replace the architecture classifier. It adds a confidence signal derived from the netlist graph. If an instance's neighbors strongly support its semantic class, the partitioner trusts the architecture preference more. If the graph context is weak, crossing and balance terms are allowed to dominate.

| Design | v2 Crossing | v3 Context Crossing | Effect |
| --- | ---: | ---: | --- |
| Ibex | 8585 | 7410 | 13.7% lower crossing than v2 |
| riscv32i | 1791 | 1800 | similar crossing with better balance |

This result suggests that graph-context semantic confidence can improve or stabilize ASA-RV3D without giving up the explainable heuristic pipeline.

## Method Overview

The current flow has six stages:

1. Run ORFS/OpenROAD baseline for a public RISC-V design.
2. Extract lightweight features from final gate-level Verilog and selected reports.
3. Classify instances into architecture-related groups.
4. Compute graph-context semantic confidence from netlist connectivity.
5. Run architecture-aware 2-tier partitioning.
6. Generate benchmark summaries, ablations, and figures.

The v2 partitioner uses a greedy local-refinement strategy inspired by FM-style partition improvement. The objective combines:

```text
crossing proxy
+ instance balance penalty
+ proxy-weight balance penalty
+ architecture placement penalty
```

The v3 context variant scales the architecture penalty by graph-context confidence:

```text
crossing proxy
+ balance penalties
+ context-weighted architecture penalty
```

## Repository Layout

```text
classifier/      Architecture semantic classifier.
configs/         Project configuration files.
docs/            Method notes and experiment documentation.
evaluation/      Metric evaluation and plotting scripts.
partition/       Tier partitioning algorithms.
results/         Lightweight CSV/JSON/SVG results committed to Git.
scripts/         Feature extraction and utility scripts.
third_party/     Reserved for external references if needed.
```

Large ORFS physical artifacts such as DEF, ODB, GDS, and SPEF are not copied into this repository. The repository stores compact, reproducible summaries instead.

## Reproduce

Run the ORFS/OpenROAD baseline outside this repository, then extract features:

```bash
python3 scripts/extract_orfs_baseline.py \
  --orfs-flow-dir ~/openroad-flow-scripts/flow \
  --design ibex \
  --output-dir results/ibex_features
```

Classify architecture semantics:

```bash
python3 classifier/architecture_classifier.py \
  --features-dir results/ibex_features
```

Compute graph-context scores:

```bash
python3 evaluation/graph_context_score.py \
  --features-dir results/ibex_features
```

Run v2 partitioning:

```bash
python3 partition/partition_v2.py \
  --features-dir results/ibex_features \
  --output-dir results/ibex_partition_v2_repaired
```

Run v3 graph-context partitioning:

```bash
python3 partition/partition_v3_context.py \
  --features-dir results/ibex_features \
  --output-dir results/ibex_partition_v3_context
```

For riscv32i, replace `ibex` and `results/ibex_features` with `riscv32i` and `results/riscv32i_features`.

## Key Outputs

```text
results/benchmark_summary/two_riscv_benchmark_partition_summary.csv
results/benchmark_summary/two_riscv_extended_baseline_summary.csv
results/benchmark_summary/v2_vs_v3_context_summary.csv
results/benchmark_summary/ibex_multi_metric_summary.csv
results/benchmark_summary/riscv32i_multi_metric_summary.csv
results/figures/summary/two_riscv_benchmark_partition_summary.svg
results/figures/summary/two_riscv_multi_metric_summary.svg
docs/asa-rv3d-method.md
docs/two-riscv-benchmark-results.md
```

## Limitations

- `crossing_connections_proxy` is a communication proxy, not a true TSV count.
- The project does not perform full 3D placement and routing.
- Architecture classification is currently rule-based.
- Graph-context scoring is a lightweight structural confidence method, not a trained GNN.
- Current evaluation covers two RISC-V designs; more benchmarks would strengthen the evidence.

## Roadmap

- Add more RISC-V benchmarks.
- Add stronger connectivity-only and random-seed baselines.
- Extend parameter sweeps to both designs.
- Improve architecture classification with hierarchy-aware and graph-aware features.
- Explore GNN-assisted scoring as an optional module.
- Add physical-aware proxies such as estimated wirelength and crossing locality.
