# Reproduction Guide

RV3D-Public provides a lightweight reproduction entrypoint for the repository's
competition-facing and research-facing results. The default path regenerates
summary indexes and consistency checks from the checked-in extracted features,
timing reports, and partition assignments.

The scripts reproduce proxy-level architecture, scenario, physical, timing, and
path-aware analyses. They do not rerun signoff 3D place-and-route, TSV or
hybrid-bonding insertion, extracted 3D parasitics, thermal analysis, or timing
closure.

## Quick Start

From the repository root:

```bash
bash scripts/reproduce_core_results.sh
```

This default mode refreshes:

- `docs/result-index.md`
- `results/benchmark_summary/result_index.csv`
- `results/benchmark_summary/paper_readiness_audit.csv`
- `results/benchmark_summary/paper_readiness_audit.md`

It also reports whether the major rollup CSV files are present.

## Reproduction Modes

Use the first argument to select a focused reproduction group:

```bash
bash scripts/reproduce_core_results.sh quick
bash scripts/reproduce_core_results.sh ablation
bash scripts/reproduce_core_results.sh downstream
bash scripts/reproduce_core_results.sh robustness
bash scripts/reproduce_core_results.sh scenario
bash scripts/reproduce_core_results.sh pseudo3d
bash scripts/reproduce_core_results.sh all
```

The modes are:

| Mode | Purpose |
| --- | --- |
| `quick` | Refresh result index and readiness audit from existing outputs. |
| `ablation` | Reproduce component and architecture-ablation summaries. |
| `downstream` | Recompute the path-aware vertical-delay downstream proxy across the configured design-scenario set. |
| `robustness` | Recompute delay-sweep and path-count-sweep robustness summaries. |
| `scenario` | Recompute scenario-behavior summaries. |
| `pseudo3d` | Recompute pseudo-3D realization proxy summaries. |
| `all` | Run all supported analysis groups, then refresh the index and audit. |

## Default Design Set

By default, the reproduction script uses the four primary design targets:

```bash
DESIGNS="riscv32i ibex picorv32 scr1_core_tuned"
```

SERV is retained as a boundary/sanity benchmark in the checked-in result index,
but it is not part of the main four-core headline set.

The default scenarios are:

```bash
SCENARIOS="control_datapath_split memory_near_logic state_and_clock_protected"
```

You can narrow a run without editing the script:

```bash
DESIGNS="ibex" SCENARIOS="state_and_clock_protected" bash scripts/reproduce_core_results.sh downstream
```

## Downstream Proxy Controls

The path-aware downstream validation uses OpenSTA path reports and injects a
fixed delay for each tier transition on matched paths.

Default settings:

```bash
MAX_PATHS=100
VERTICAL_DELAY_NS=0.05
```

Override them as needed:

```bash
MAX_PATHS=200 VERTICAL_DELAY_NS=0.10 bash scripts/reproduce_core_results.sh downstream
```

## Expected Result Groups

The repository index tracks these main result groups:

| Result group | Main outputs |
| --- | --- |
| Four-core timing-regret result | `results/benchmark_summary/timing_regret_guarded_four_core_summary.csv` |
| Pseudo-3D realization proxy | `results/benchmark_summary/pseudo3d_realization_rollup.csv` |
| Path-aware downstream proxy | `results/benchmark_summary/path_aware_downstream_vertical_delay_rollup.csv` |
| Component ablation | `results/benchmark_summary/component_ablation_rollup.csv` |
| Architecture ablation | `results/benchmark_summary/architecture_ablation_rollup.csv` |
| Robustness sweeps | `results/benchmark_summary/path_aware_downstream_delay_sweep_rollup.csv`, `results/benchmark_summary/path_aware_downstream_pathcount_sweep_rollup.csv` |
| Scenario behavior | `results/benchmark_summary/scenario_behavior_rollup.csv` |
| Result index | `docs/result-index.md`, `results/benchmark_summary/result_index.csv` |

For a compact map from claims to files, read:

```bash
docs/result-index.md
```

## Full ORFS/OpenROAD Inputs

The quick reproduction flow assumes that ORFS/OpenROAD final artifacts have
already been generated and converted into feature CSVs. A full from-RTL run is
heavier and depends on a working OpenROAD-flow-scripts installation.

The project currently uses:

- sky130hd ORFS/OpenROAD outputs,
- gate-level feature extraction,
- architecture semantic recovery,
- DEF-derived physical proxies,
- OpenSTA timing-path reports,
- TritonPart initial assignments,
- ASA-RV3D guarded repair assignments.

SCR1 uses a tuned 20 ns ORFS configuration because the earlier quick SCR1
configuration did not close timing. This is intentionally documented so that
benchmark quality is not improved by silently accepting broken timing closure.

## Scope

These reproduction scripts support early-stage 3D-aware partition analysis.
They are intended to make the repository easy to audit and rerun, not to claim
full 3D physical-design signoff.
