# Paper Artifact Manifest

This directory records the result snapshot used in the ASA-RV3D manuscript, "Constrained Post-Partition Refinement for RISC-V 3-D Tier Partitioning."

The files in this directory are paper-facing artifacts and are frozen together with the manuscript version. They are intended to provide an explicit mapping between the numbers reported in the paper and the public repository.

- `table2_partition_results.csv` corresponds to the partition-level Context-OFF / Context-ON results reported in Table 2.
- `table3_path_validation.csv` corresponds to the downstream path-level validation reported in Table 3.

The main paper comparison uses PicoRV32 and riscv32i. `scr1_core_tuned` is retained as a boundary-case benchmark: its imported native timing-aware assignment is mildly infeasible under the reconstructed area criterion, and `scr1_feasibility_restoration.csv` records the guarded feasibility-restoration pre-stage used to recover the strict area window. SCR1 remains outside the primary six-case Context-OFF / Context-ON comparison.

Historical development outputs and exploratory experiments remain under `results/` and `docs/`. They may use earlier terminology, metrics, or intermediate method variants and should not be interpreted as the final paper-facing result definition.

For the paper-facing interpretation of the method and results, use the files under this directory together with the top-level `README.md`.

Important provenance note: these tables record the manuscript-reported snapshot. They should not be read as a guarantee that every historical generated CSV currently under `results/` regenerates the exact same values without additional provenance context.

## SCR1 Baseline Feasibility Restoration Snapshot

- `scr1_feasibility_restoration.csv`: frozen paper-facing snapshot for SCR1 native-baseline feasibility restoration. This snapshot records the reconstructed area-window violation and the guarded minimal restoration result; it does not modify Table 2 or Table 3.
