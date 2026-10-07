# Reproduction Guide

This guide describes the paper-facing ASA-RV3D public artifact. The repository is organized around a checked-in snapshot of scripts, extracted features, assignments, and summary CSV files used to audit the manuscript results.

The lightweight reproduction path does not rerun full OpenROAD-flow-scripts implementation, signoff 3-D placement and routing, TSV or hybrid-bonding insertion, extracted 3-D parasitics, thermal analysis, IR-drop closure, or final timing closure.

## Quick Start

From the repository root, the paper-facing snapshot can be checked with:

```bash
python3 scripts/audit_paper_snapshot.py
bash scripts/reproduce_core_results.sh quick
```

The first command validates the manuscript-facing files and frozen values under `paper/`. The second command runs the same snapshot audit together with the retained repository-level consistency checks and historical result-index refresh steps.

The paper-facing source of truth is:

- `paper/table2_partition_results.csv`
- `paper/table3_path_validation.csv`
- `paper/scr1_feasibility_restoration.csv`
- `paper/artifact_manifest.md`

The first two CSV files record the primary PicoRV32 and riscv32i results. `scr1_feasibility_restoration.csv` separately records the SCR1 boundary-case restoration result and does not extend the primary Context-OFF / Context-ON comparison.

Generated and retained outputs under `results/` provide supporting provenance and inspection data, but they may include historical experiment families or intermediate terminology. They should not replace the frozen files under `paper/` as the manuscript-facing source of truth.

## Paper-Facing Scope

The primary comparable paper snapshot uses two RISC-V designs:

```bash
PAPER_DESIGNS="picorv32 riscv32i"
```

The manuscript scenarios are:

```bash
SCENARIOS="control_datapath_split memory_near_logic state_and_clock_protected"
```

These two designs and three scenarios form the six design-scenario pairs used for the primary Context-OFF / Context-ON comparison.

`scr1_core_tuned` is retained separately as a boundary-case feasibility-restoration study. Its imported native timing-aware assignment has a reconstructed tier-0 area fraction of `0.520588`, slightly outside the prescribed `0.48-0.52` interval. The guarded restoration stage reaches `0.519990` after five instance moves, with raw crossings changing from `272` to `276`, corresponding to `0.014706` raw-cut regret relative to the original native assignment, while the evaluated mean and worst tier-transition guard deltas remain zero.

SCR1 therefore demonstrates recovery of one mildly infeasible imported baseline under the retained guards. It remains outside the primary six-case Context-OFF / Context-ON comparison and should not be interpreted as evidence that arbitrary or severely imbalanced native assignments can always be restored.

Ibex and other older assets are retained only as historical development artifacts and are not part of the manuscript-facing comparison.

## Reproduction Modes

The main reproduction script supports several retained analysis modes:

```bash
bash scripts/reproduce_core_results.sh quick
bash scripts/reproduce_core_results.sh ablation
bash scripts/reproduce_core_results.sh downstream
bash scripts/reproduce_core_results.sh robustness
bash scripts/reproduce_core_results.sh scenario
bash scripts/reproduce_core_results.sh pseudo3d
bash scripts/reproduce_core_results.sh all
```

Use `quick` for the public paper-artifact sanity check. The other modes are retained for broader development and supporting analyses and may touch result families beyond the final paper snapshot.

| Mode | Scope |
| --- | --- |
| `quick` | Audit the frozen paper snapshot, refresh retained indexes and audits, and check major retained rollups. |
| `ablation` | Recompute retained component and context-ablation summaries. |
| `downstream` | Recompute the retained path-aware vertical-delay proxy for configured design and scenario sets. |
| `robustness` | Recompute retained delay-sweep and path-count-sweep robustness summaries. |
| `scenario` | Recompute retained scenario-behavior summaries. |
| `pseudo3d` | Recompute retained pseudo-3-D realization proxy summaries. |
| `all` | Run all retained analysis groups and then refresh the quick consistency checks. |

The native-baseline feasibility-restoration study is reproduced separately from these modes. To refresh the native feasibility audit without changing an assignment, run:

```bash
bash scripts/run_baseline_feasibility_restoration.sh audit
```

To rerun the SCR1 area-only and guarded feasibility-restoration policies under the retained raw-cut and timing-path guard settings, run:

```bash
bash scripts/run_baseline_feasibility_restoration.sh restore
```

To verify that the restoration stage is a strict no-op for the already feasible PicoRV32 and riscv32i native assignments, run:

```bash
bash scripts/run_baseline_restoration_noop_regression.sh
```

These restoration scripts use the original native TritonPart assignment as the reference for raw-cut and timing-path guard evaluation. The restored SCR1 assignment does not establish a new guard budget for subsequent refinement.

The frozen manuscript-facing restoration values remain those recorded in `paper/scr1_feasibility_restoration.csv`.

## Optional Environment Overrides

Historical/development modes accept environment overrides:

```bash
DESIGNS="picorv32 riscv32i" \
SCENARIOS="control_datapath_split memory_near_logic state_and_clock_protected" \
MAX_PATHS=100 \
VERTICAL_DELAY_NS=0.05 \
bash scripts/reproduce_core_results.sh downstream
```

These overrides are for rerunning retained scripts. They do not redefine the paper snapshot under `paper/`.

## What The Artifact Reproduces

The public artifact supports:

- consistency checks for the frozen partition-level Context-OFF / Context-ON snapshot in `paper/table2_partition_results.csv`;
- consistency checks for the downstream path-level validation snapshot in `paper/table3_path_validation.csv`;
- consistency checks for the SCR1 boundary-case feasibility-restoration snapshot in `paper/scr1_feasibility_restoration.csv`;
- inspection of retained Context-OFF and Context-ON assignments and supporting summaries;
- reproduction of the SCR1 native-baseline feasibility audit and guarded restoration experiment;
- verification that the restoration stage leaves already feasible PicoRV32 and riscv32i native assignments unchanged;
- retained historical result indexes, readiness checks, and supporting proxy-analysis scripts.

The lightweight public reproduction path does not rerun the complete OpenROAD-flow-scripts physical-design flow from RTL, nor does it claim signoff-quality 3-D placement and routing, TSV or hybrid-bonding insertion, extracted 3-D parasitics, thermal analysis, IR-drop closure, or final routed PPA.

The downstream vertical-link-delay study should therefore be interpreted as a controlled path-level proxy rather than as post-route 3-D timing signoff. Likewise, the SCR1 restoration result demonstrates recovery of one mildly infeasible imported baseline under the evaluated reconstructed-area, raw-cut, and timing-path constraints; it does not establish general recovery for arbitrary infeasible partitions.

For manuscript-facing numerical claims, the files under `paper/` remain the authoritative frozen snapshot. Outputs under `results/` provide supporting provenance and reproducibility evidence but may also contain historical or development-stage experiments outside the final paper scope.
