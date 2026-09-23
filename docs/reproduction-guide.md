# Reproduction Guide

RV3D-Public reproduces the core analysis from existing ORFS/OpenROAD final artifacts.

## Prerequisites

- ORFS workspace: `~/openroad-flow-scripts/flow`
- Required designs: `ibex`, `riscv32i`, `picorv32`
- Required final artifacts: `6_final.v`, `6_final.def`, `6_final.odb`, `6_final.sdc`, `6_final.spef` under `results/sky130hd/<design>/base/`.

## Run

```bash
./scripts/reproduce_core_results.sh
```

Optional overrides:

```bash
ORFS_FLOW_DIR=/path/to/openroad-flow-scripts/flow ./scripts/reproduce_core_results.sh
DESIGNS="ibex picorv32" ./scripts/reproduce_core_results.sh
SCENARIOS="state_and_clock_protected" ./scripts/reproduce_core_results.sh
```

## What It Reproduces

1. Feature extraction.
2. Architecture classification and mapping.
3. Graph, physical, and timing context extraction.
4. TritonPart baseline import/export.
5. No-timing-guard ablation and complete ASA-RV3D.
6. Timing-crossing summaries.
7. Final result table and SVG figures.

## What It Does Not Do

It does not rerun the full ORFS RTL-to-GDS flow. Full backend runs are slower and can hit the known headless GUI-report failure at the final report stage.

## Main Outputs

- `results/benchmark_summary/timing_regret_guarded_three_riscv_summary.csv`
- `results/benchmark_summary/final_main_result_table.md`
- `results/figures/final/*_timing_weighted_crossing.svg`

## Claim Boundary

The reproduced results are proxy-level architecture/scenario/physical/timing repair results. They are not signoff 3D placement/routing, TSV or hybrid-bonding PPA, or full timing-closure claims.

<!-- PSEUDO3D_REALIZATION:START -->
## Pseudo-3D Realization

After timing-regret ASA-RV3D assignments have been generated, run:

```bash
python3 evaluation/evaluate_pseudo3d_realization.py
python3 evaluation/plot_pseudo3d_realization.py
python3 evaluation/export_pseudo3d_layout.py
```

The first command evaluates vertical-risk metrics, the second draws the final timing-risk reduction figure, and the third exports tier0/tier1 pseudo-layout artifacts plus vertical interconnect candidates.
<!-- PSEUDO3D_REALIZATION:END -->

<!-- PATH_AWARE_DOWNSTREAM_START -->
## Reproducing Path-Aware Downstream Validation

After generating TritonPart, timing-regret ASA-RV3D, OpenSTA timing reports, and path-aware repair assignments, run:

```bash
python3 evaluation/evaluate_path_aware_downstream_vertical_delay.py --design ibex --scenario state_and_clock_protected --max-paths 100 --vertical-delay-ns 0.05
```

The aggregate outputs are:

- `results/benchmark_summary/path_aware_downstream_vertical_delay_summary.csv`
- `results/benchmark_summary/path_aware_downstream_vertical_delay_rollup.csv`
- `results/benchmark_summary/path_aware_tradeoff_summary.csv`
- `results/benchmark_summary/path_aware_tradeoff_rollup.csv`
<!-- PATH_AWARE_DOWNSTREAM_END -->

