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
5. Guarded repair and timing-regret guarded repair.
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
