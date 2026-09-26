# RV3D-Public

RV3D-Public is a reproducible research prototype for architecture-aware early-stage 3D partitioning of RISC-V gate-level netlists. The current paper-facing flow uses native timing-aware TritonPart as the strong baseline, then applies normalized dynamic ASA-RV3D Phase-3 refinement. Candidate moves are recomputed from the current assignment, and accepted only when they preserve reconstructed area balance, raw-cut/path guards, and canonical timing-risk feasibility.

The repository is intended to support both RISC-V competition review and research reuse. It is not a signoff 3D physical-design tool: the reported metrics are early-stage partitioning, architecture-structural, timing-risk, and vertical-delay proxy metrics rather than TSV/hybrid-bonding signoff, full 3D routing, thermal closure, or final PPA claims.

## What This Repository Provides

- Native timing-aware TritonPart baselines for public RISC-V cores.
- Normalized dynamic ASA-RV3D Phase-3 constrained refinement over those baselines.
- RISC-V architecture semantic recovery for gate-level instances.
- OpenROAD/OpenSTA-derived physical and timing context.
- Architecture ON/OFF ablations under the same area, cut, path, and timing guards.
- Canonical crossing, timing-crossing, architecture-structural, and downstream vertical-delay proxy validation.
- Paper-facing summaries for PicoRV32 and riscv32i, with SCR1 retained as strict-area-window boundary evidence and Ibex retained as a documented pending/legacy case.
- Reproducible result summaries, figures, and navigation indices for competition review and research reuse.

## Main Result Snapshot

- Normalized dynamic Phase-3 uses current-state move gains rather than replaying an old ASA trace.
- Across the current nine design-scenario rows, six are primary comparable PicoRV32/riscv32i cases and three SCR1 rows are retained as boundary evidence because the native timing-aware baseline is already outside the strict reconstructed area window.
- In the primary comparable set, Phase-3 preserves area, cut, and timing-path guards while reducing canonical timing-risk or structural risk in the reported evidence categories.
- Architecture semantics should be interpreted as a scenario-specific structural bias, not as a guarantee of lower generic cut or timing metrics in every case.
- The downstream vertical-delay proxy is an independent path-level validation layer for the final normalized assignments, not the checkpoint-selection criterion.

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
Native timing-aware TritonPart 2-way assignment
+ normalized ASA-RV3D architecture/scenario/physical/timing objective
+ dynamic current-state candidate recomputation
+ area, raw-cut, timing-path, and canonical timing-risk guards
+ convergence-based stopping
= normalized dynamic Phase-3 ASA-RV3D assignment
```

TritonPart provides the strong connectivity/timing-aware starting point. ASA-RV3D does not claim raw-cut superiority over TritonPart in general. Instead, it performs guarded local refinement when current-state candidate moves improve the normalized architecture/scenario/physical/timing objective while preserving feasibility constraints.

The final Phase-3 objective evaluates:

- scenario-specific architecture-risk proxies from `configs/3d_integration_scenarios.yaml`,
- RISC-V architecture-unit and semantic-group preferences,
- coverage-gated physical-context crossing risk,
- OpenSTA-derived timing-context crossing risk,
- reconstructed area balance and architecture-weight balance,
- path-level timing-fragmentation guards.

Architecture-OFF is retained as a controlled ablation: it uses the same dynamic search and guards, but disables architecture semantics. Its objective values are not directly comparable to Architecture-ON objective values, so ON/OFF claims are made through shared canonical metrics instead.

## Historical Physical-Context Ablation: TritonPart + ASA-RV3D

This table is retained as historical physical-context ablation evidence, not as the final paper-facing main result. It compares TritonPart initial assignments against ASA-RV3D guarded repair before the later timing-regret, path-aware, and normalized dynamic Phase-3 extensions became the main flow.

Across 12 design-scenario cases on four RISC-V cores, the historical flow reduces timing-weighted crossings in every case. The reduction ranges from 0.72% to 12.09%, with a mean reduction of 7.30%.

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

Primary historical data file: `results/benchmark_summary/timing_regret_guarded_four_riscv_summary.csv`.

## SERV Boundary Benchmark

SERV is retained as a small serial RISC-V boundary benchmark. Unlike the larger headline cores, TritonPart already produces a very small timing-crossing footprint on SERV. ASA-RV3D improves the guarded objective by 1.57% to 5.83% across the three scenarios while keeping timing-weighted crossing nearly unchanged, with at most 0.32% degradation. This result is used as a guardrail sanity check rather than as a headline improvement case.

## Historical Timing Guard Ablation

The repository keeps a `No timing guard` ablation. It uses the same TritonPart starting point and the same architecture/scenario/physical repair machinery as ASA-RV3D, but disables OpenSTA-derived timing-regret rejection.

This ablation is not the final algorithm. It is used to show that architecture/scenario/physical repair can improve a proxy objective while accidentally increasing timing-sensitive crossings. Later guarded flows add timing-risk feasibility constraints and are the results used in the main method line.

Figure legend convention:

- `TritonPart`: strong hypergraph partition baseline.
- `No timing guard`: ASA-RV3D ablation without timing-regret rejection.
- `ASA-RV3D`: complete guarded method.

## Internal ASA-RV3D-Only Result

The repository also includes the standalone v4b guarded physical-context partitioner, `partition_v4b_physical_guarded.py`. This version starts from a scenario-aware assignment rather than from TritonPart. It is useful as an ablation showing that guarded physical-context refinement is beneficial even without a mature hypergraph backend.

## Method Overview

The current paper-facing flow has nine stages:

1. Run ORFS/OpenROAD and collect compact netlist, placement, and timing artifacts.
2. Build or import a native timing-aware TritonPart 2-way assignment.
3. Extract compact gate-level features from final Verilog and selected reports.
4. Recover RISC-V architecture units and semantic groups for instances.
5. Compute physical and timing context scores.
6. Evaluate normalized Phase-3 candidate moves from the current assignment.
7. Accept only moves that preserve area, cut, timing-path, and canonical timing-risk guards.
8. Stop by convergence or no legal improving move.
9. Generate canonical crossing, structural, downstream, and readiness summaries.

## Repository Layout

<!-- PSEUDO3D_REALIZATION:START -->
## Pseudo-3D Realization

ASA-RV3D includes a pseudo-3D realization stage. This is not true 3D place-and-route. It interprets each 2-tier assignment as an early 3D stack, then evaluates cross-tier vertical-link risk using architecture, timing, and physical context.

The pseudo-3D outputs are retained as validation and presentation assets. They should be interpreted as early cross-tier risk proxies, not signoff TSV insertion, 3D routing, parasitic extraction, or thermal analysis.
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

For the final normalized dynamic Phase-3 flow, the main scripts are:

```bash
bash scripts/run_normalized_dynamic_convergence_phase3.sh
bash scripts/run_normalized_dynamic_convergence_evaluation.sh
python3 scripts/run_normalized_dynamic_downstream_delay_sweep.py
python3 scripts/summarize_phase3_method_freeze.py
```

Example for one Phase-3 refinement after features and native timing-aware TritonPart assignment exist:

```bash
python3 partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py \
  --design picorv32 \
  --scenario state_and_clock_protected \
  --initial-assignment results/picorv32_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv \
  --features-dir results/picorv32_features \
  --instance-area results/benchmark_summary/picorv32_openroad_instance_area.csv \
  --timing-report results/timing_reports/picorv32_report_checks_max.rpt \
  --max-paths 100 \
  --max-iterations 300 \
  --max-cut-regret 0.05 \
  --max-pavg-regret 0.0 \
  --max-pwst-delta 0.0 \
  --convergence-window 10 \
  --min-relative-gain 0.001 \
  --checkpoint-every 10 \
  --output-dir results/picorv32_tritonpart_compatible_normalized_dynamic_convergence_guarded_repair/state_and_clock_protected
```

## Key Outputs

```text
results/benchmark_summary/normalized_dynamic_convergence_phase3_summary.csv
results/benchmark_summary/normalized_dynamic_convergence_phase3_rollup.csv
results/benchmark_summary/normalized_dynamic_convergence_canonical_summary.csv
results/benchmark_summary/normalized_dynamic_convergence_canonical_rollup.csv
results/benchmark_summary/phase3_method_freeze_summary.csv
results/benchmark_summary/phase3_method_freeze_rollup.csv
results/benchmark_summary/normalized_dynamic_downstream_delay_sweep_summary.csv
results/benchmark_summary/normalized_dynamic_downstream_delay_sweep_rollup.csv
results/benchmark_summary/paper_readiness_audit.md
```

## Normalized Dynamic Phase-3

The current final method line is the normalized dynamic Phase-3 flow. It starts from OpenROAD native timing-aware TritonPart assignments and recomputes candidate moves from the current assignment at every step. Candidate moves are accepted only when they preserve reconstructed OpenROAD area balance, raw-cut guards, timing-path guards, and canonical timing-risk feasibility.

The main paper-facing summaries are:

- `results/benchmark_summary/normalized_dynamic_convergence_phase3_summary.csv`
- `results/benchmark_summary/normalized_dynamic_convergence_canonical_summary.csv`
- `results/benchmark_summary/phase3_method_freeze_summary.csv`

Interpretation discipline:

- PicoRV32 and riscv32i are the primary comparable strong-baseline designs.
- SCR1 is retained as boundary evidence because the native timing-aware baseline is already outside the strict reconstructed area-balance window.
- Ibex is retained as a legacy/pending documented case rather than as a current normalized Phase-3 headline result.
- `riscv32i/memory_near_logic` is marked weak-semantic-coverage for architecture-semantics claims.
- `picorv32/control_datapath_split` is retained as a diagnostic anomaly where Architecture-ON improves over native but Architecture-OFF is stronger on several shared metrics.

## Limitations

- ASA-RV3D is a partitioning and feasibility-analysis prototype, not a complete 3D physical design tool.
- `crossing_connections_proxy`, timing-weighted crossing, structural crossing, and downstream vertical-delay degradation are communication/risk proxies, not signoff TSV, hybrid-bonding, thermal, power, or IR-drop metrics.
- Physical context uses DEF placement, fanout, HPWL, and observability proxies; it is not full 3D placement and routing.
- SCR1 is boundary evidence in the normalized Phase-3 study because the native timing-aware baseline is outside the strict reconstructed 48/52 area window.
- Ibex remains a documented legacy/pending case for the final normalized strong-baseline flow.
- Architecture classification is rule-based with graph, physical, and timing confidence signals; it is not a trained GNN.

## Roadmap

- Keep the normalized dynamic Phase-3 method frozen unless a correctness bug is found.
- Add another fully comparable strong-baseline design only if it can pass the same native timing-aware TritonPart and area-window checks.
- Keep downstream and pseudo-3D analyses as validation layers, not as signoff claims.
- Improve runtime engineering without changing the reported objective or guard semantics.

<!-- PATH_AWARE_DOWNSTREAM_START -->
## Normalized Dynamic Downstream Validation

The current downstream validation is a path-level proxy rather than signoff 3D STA. It injects fixed vertical-link delay values on OpenSTA max paths and compares native timing-aware TritonPart, normalized dynamic Architecture-ON, and normalized dynamic Architecture-OFF assignments.

Across the current PicoRV32/riscv32i primary comparable downstream sweep, Architecture-ON does not increase crossing-path fraction versus native, reduces mean tier transitions by 0.03 on average, leaves WNS-degradation proxy unchanged, and reduces the TNS-degradation proxy increasingly as vertical-link delay grows. Architecture-ON and Architecture-OFF are similar under this downstream proxy, so downstream results are used as feasibility validation rather than as evidence that architecture semantics always beats generic repair.

Primary files:

- `results/benchmark_summary/normalized_dynamic_downstream_delay_sweep_summary.csv`
- `results/benchmark_summary/normalized_dynamic_downstream_delay_sweep_rollup.csv`

These results should be presented as independent downstream proxy evidence, not as full 3D signoff timing closure.
<!-- PATH_AWARE_DOWNSTREAM_END -->
