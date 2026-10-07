# ASA-RV3D Paper Artifacts

This directory contains the manuscript-facing result snapshot for:

> **Constrained Post-Partition Refinement for RISC-V 3-D Tier Partitioning**

The files under `paper/` are the authoritative frozen source for numerical claims reported in the manuscript. They provide a compact mapping between the paper and the public ASA-RV3D repository. Historical and intermediate outputs under `results/` may contain additional experiment families or earlier terminology and should not be used in place of these paper-facing snapshots.

## Files

- `artifact_manifest.md`: provenance, interpretation, and scope of the manuscript-facing artifacts.
- `table2_partition_results.csv`: primary partition-level Native / Context-OFF / Context-ON result snapshot for PicoRV32 and riscv32i across the three evaluated design-context scenarios.
- `table3_path_validation.csv`: downstream path-level validation snapshot for PicoRV32 and riscv32i.
- `scr1_feasibility_restoration.csv`: separate boundary-case snapshot for guarded feasibility restoration of the mildly infeasible `scr1_core_tuned` native assignment.

## Primary Comparison

The primary Context-OFF / Context-ON comparison consists of two RISC-V designs:

- PicoRV32;
- riscv32i.

Each design is evaluated under three scenarios:

- control/datapath;
- memory-near-logic;
- state/clock.

These two designs and three scenarios form the six design-scenario pairs recorded in `table2_partition_results.csv`.

The downstream path-level results for the same two primary designs are recorded in `table3_path_validation.csv`.

## SCR1 Boundary-Case Restoration

`scr1_core_tuned` is retained separately as a feasibility-restoration case study and is **not** added to the primary six-case Context-OFF / Context-ON comparison.

Its imported native timing-aware assignment has a reconstructed tier-0 area fraction of `0.520588`, slightly outside the prescribed `0.48-0.52` interval. The optional guarded restoration stage reaches a feasible tier-0 area fraction of `0.519990` after five instance moves. Raw crossing nets change from `272` to `276`, corresponding to a raw-cut regret of `0.014706` relative to the original native assignment, while the evaluated mean and worst tier-transition guard deltas remain zero.

The frozen values for this boundary case are stored in:
```text
paper/scr1_feasibility_restoration.csv
```

The restoration stage is scenario independent and does not use recovered design context. The original native TritonPart assignment remains the reference for raw-cut and timing-path guard budgets; restoration does not reset those budgets before subsequent refinement.

This result demonstrates recovery of one mildly infeasible imported baseline under the evaluated guards. It should not be interpreted as evidence that arbitrary or severely imbalanced native assignments can always be restored.

## Interpretation and Provenance

For detailed interpretation of the paper-facing artifacts, use:
```text
paper/artifact_manifest.md
```

For the corresponding method and reproduction descriptions, see:
```text
README.md
docs/method.md
docs/reproduction-guide.md
```

The paper-facing snapshot can be checked with:
```bash
python3 scripts/audit_paper_snapshot.py
```

The files under `paper/` are frozen manuscript-facing snapshots. Supporting outputs under `results/` provide additional provenance and reproducibility evidence but may also include historical or development-stage experiments outside the final paper scope.
