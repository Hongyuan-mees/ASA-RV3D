# Paper Artifact Manifest

This directory contains the manuscript-facing result snapshot for **ASA-RV3D**, associated with the manuscript:

> **Constrained Post-Partition Refinement for RISC-V 3-D Tier Partitioning**

The files under `paper/` are the authoritative frozen source for numerical claims reported in the manuscript. They provide a compact mapping between the paper and the public repository and should be preferred over historical or intermediate outputs under `results/`.

## Primary Paper Snapshots

### `table2_partition_results.csv`

This file records the primary partition-level comparison among:

- Native timing-aware TritonPart;
- Context-OFF;
- Context-ON.

The primary comparison uses **PicoRV32** and **riscv32i** under three design-context scenarios:

- control/datapath;
- memory-near-logic;
- state/clock.

These two designs and three scenarios form the six design-scenario pairs used for the manuscript's Context-OFF / Context-ON analysis.

The snapshot records raw crossing nets, scenario-sensitive crossing nets, and context gain. It remains unchanged by the separate SCR1 feasibility-restoration study.

### `table3_path_validation.csv`

This file records the downstream path-level validation for PicoRV32 and riscv32i.

The snapshot includes:

- crossing-path fraction;
- mean tier transitions;
- maximum tier transitions;
- total-negative-slack degradation proxies under fixed vertical-link delays of 20, 50, and 100 ps.

These quantities are evaluation proxies based on retained OpenSTA maximum-delay paths. They are not presented as signoff-quality post-route 3-D timing results.

## SCR1 Baseline Feasibility Restoration Snapshot

### `scr1_feasibility_restoration.csv`

`scr1_core_tuned` is retained separately as a boundary-case feasibility-restoration study and is **not** added to the primary six-case Context-OFF / Context-ON comparison.

Its imported native timing-aware assignment is mildly infeasible under the reconstructed OpenROAD-area criterion:

- native tier-0 area fraction: `0.520588`;
- prescribed area interval: `0.48-0.52`.

The guarded feasibility-restoration pre-stage reaches:

- restored tier-0 area fraction: `0.519990`;
- accepted instance moves: `5`;
- raw crossing nets: `272 -> 276`;
- raw-cut regret relative to the original native assignment: `0.014706`;
- mean tier-transition regret: `0.000000`;
- worst tier-transition increase: `0.000000`;
- guard status: `pass`.

The restoration stage is scenario independent and does not use recovered design context. Its purpose is to recover the required starting feasibility before normal ASA-RV3D refinement.

The original native TritonPart assignment remains the reference for raw-cut and timing-path guard budgets; restoration does not reset those budgets before subsequent refinement.

The available retained artifacts establish that the imported SCR1 native assignment is mildly infeasible under ASA-RV3D's reconstructed OpenROAD-area criterion. They do **not** establish a specific mismatch between TritonPart's internal balance definition and the reconstructed area criterion.

This SCR1 result demonstrates recovery of one mildly infeasible imported baseline under the evaluated guards. It should not be interpreted as evidence that arbitrary or severely imbalanced native assignments can always be restored.

## Provenance and Scope

The files in this directory are manuscript-facing snapshots rather than a claim that every historical CSV under `results/` will independently regenerate the same values without the corresponding experiment configuration and provenance.

Supporting implementation, audit, and reproduction utilities are retained elsewhere in the repository. In particular, the SCR1 restoration study is supported by the native-baseline feasibility audit, the guarded restoration implementation, and the no-op regression on the already feasible PicoRV32 and riscv32i native assignments.

Historical development outputs and exploratory experiments remain under `results/` and `docs/archive/`. They may contain earlier terminology, intermediate algorithm variants, or experiment families outside the final manuscript scope and should not be treated as the paper-facing source of truth.

For manuscript-facing interpretation, use this manifest together with:

- `paper/table2_partition_results.csv`;
- `paper/table3_path_validation.csv`;
- `paper/scr1_feasibility_restoration.csv`;
- the top-level `README.md`;
- `docs/method.md`;
- `docs/reproduction-guide.md`.

The paper-facing snapshot can be checked with:
```bash
python3 scripts/audit_paper_snapshot.py
```
