# Reproduction Guide

This guide describes the paper-facing ASA-RV3D public artifact. The repository is organized around a checked-in snapshot of scripts, extracted features, assignments, and summary CSV files used to audit the manuscript results.

The lightweight reproduction path does not rerun full OpenROAD-flow-scripts implementation, signoff 3-D placement and routing, TSV or hybrid-bonding insertion, extracted 3-D parasitics, thermal analysis, IR-drop closure, or final timing closure.

## Quick Start

From the repository root:

```bash
python3 scripts/audit_paper_snapshot.py
bash scripts/reproduce_core_results.sh quick
```

The first command checks the manuscript-facing snapshot under `paper/`. The second command runs the same paper snapshot audit, refreshes the retained historical result index, refreshes the historical readiness audit, and checks that major retained rollup files are present.

The paper-facing source of truth is:

- `paper/table2_partition_results.csv`
- `paper/table3_path_validation.csv`
- `paper/artifact_manifest.md`

Generated and retained development outputs under `results/` are useful for provenance and inspection, but they may include earlier method names or intermediate experiment families.

## Paper-Facing Scope

The primary comparable paper snapshot uses two RISC-V designs:

```bash
PAPER_DESIGNS="picorv32 riscv32i"
```

The manuscript scenarios are:

```bash
SCENARIOS="control_datapath_split memory_near_logic state_and_clock_protected"
```

SCR1 tuned artifacts are retained as boundary evidence because the reconstructed area window prevents a primary comparable success case. Ibex and other older assets are retained as historical development artifacts, not as primary manuscript evidence.

## Reproduction Modes

The main script supports several modes:

```bash
bash scripts/reproduce_core_results.sh quick
bash scripts/reproduce_core_results.sh ablation
bash scripts/reproduce_core_results.sh downstream
bash scripts/reproduce_core_results.sh robustness
bash scripts/reproduce_core_results.sh scenario
bash scripts/reproduce_core_results.sh pseudo3d
bash scripts/reproduce_core_results.sh all
```

Use `quick` for the public artifact sanity check. The other modes are retained for development and historical analyses; they may touch broader result families than the final paper snapshot.

| Mode | Scope |
| --- | --- |
| `quick` | Audit the paper snapshot, refresh retained indexes/audits, and check major rollups. |
| `ablation` | Recompute retained component and architecture-ablation summaries. |
| `downstream` | Recompute the retained path-aware vertical-delay proxy for configured design/scenario sets. |
| `robustness` | Recompute retained delay-sweep and path-count-sweep robustness summaries. |
| `scenario` | Recompute retained scenario-behavior summaries. |
| `pseudo3d` | Recompute retained pseudo-3D realization proxy summaries. |
| `all` | Run all retained analysis groups and then refresh quick checks. |

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

- consistency checks for the manuscript Table 2 and Table 3 snapshots;
- inspection of Context-OFF and Context-ON assignments;
- path-level downstream validation summaries;
- retained historical result indexes and readiness checks;
- scripts used to generate and audit supporting proxy metrics.

The artifact does not claim signoff-quality 3-D physical implementation or final routed PPA. It is an early-stage constrained partition-refinement artifact built on checked-in gate-level, timing, and assignment data.
