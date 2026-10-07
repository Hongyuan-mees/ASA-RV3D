# ASA-RV3D

**ASA-RV3D** is a constrained post-partition refinement framework for two-tier RISC-V gate-level partitioning. It starts from a native timing-aware TritonPart assignment and explores local instance moves using normalized physical and timing information, with recovered RISC-V design context introduced as an optional guidance term.

The method is designed to improve a strong timing-aware baseline without discarding the properties already established by the underlying partitioner. Candidate moves are accepted only when they satisfy explicit area, raw-cut, and timing-path feasibility guards.

This repository contains the implementation, experiment scripts, and paper-facing artifacts associated with the manuscript:

> **Constrained Post-Partition Refinement for RISC-V 3-D Tier Partitioning**

---

## Method Overview

ASA-RV3D operates after native timing-aware TritonPart partitioning:

```text
Native timing-aware TritonPart assignment
        |
        v
Gate-level + physical + timing information
        |
        v
Normalized instance-level refinement weights
        |
        v
Risk-weighted local move evaluation
        |
        v
Area / raw-cut / timing-path feasibility guards
        |
        v
Greedy constrained refinement
        |
        v
Refined two-tier assignment
```

For each movable instance, ASA-RV3D combines three normalized components:

- recovered RISC-V design context;
- physical context derived from OpenROAD artifacts;
- timing context derived from OpenSTA/OpenROAD information.

Two controlled configurations are used in the paper:

- **Context-OFF** retains the physical and timing components while disabling recovered design context;
- **Context-ON** enables all three components under the same feasibility guards.

The recovered design context is used as soft guidance rather than as a hard architectural partitioning constraint.

A longer paper-facing method note is available at:

```text
docs/method.md
```

---

## Refinement Constraints

A locally improving move is accepted only when it remains feasible with respect to the native timing-aware TritonPart baseline.

The paper uses the following settings:

- reconstructed tier-0 area fraction: **0.48-0.52**;
- maximum raw-crossing regret: **5%**;
- OpenSTA maximum-delay paths: up to **100**;
- mean tier-transition regret limit: **0**;
- worst tier-transition increase limit: **0**;
- maximum refinement budget: **300 iterations**;
- convergence window: **10 accepted moves**;
- minimum recent relative gain: **1e-3**.

These constraints separate candidate quality from candidate feasibility: the refinement objective ranks local moves, while the guards protect the baseline area, cut, and timing-path properties.

---

## Design Context

The current implementation uses an explainable rule-based recovery procedure to associate synthesized gate-level instances with coarse RISC-V functional units and semantic groups.

The paper evaluates three design-context scenarios:

- **control/datapath**;
- **memory-near-logic**;
- **state/clock**.

These scenarios provide different soft preferences during Context-ON refinement. They do not force complete architectural blocks onto a specific tier.

---

## Paper Benchmarks

The main paper comparison uses:

| Design | Instances | Nets | Reconstructed area (um^2) |
| --- | ---: | ---: | ---: |
| PicoRV32 | 6,779 | 6,868 | 95,512 |
| riscv32i | 5,737 | 5,819 | 76,420 |

`scr1_core_tuned` is retained as a boundary-case restoration study. Its imported native timing-aware assignment is mildly outside the strict reconstructed area window; `paper/scr1_feasibility_restoration.csv` records the guarded feasibility-restoration pre-stage (`0.520588 -> 0.519990`, 5 moves, 1.47% raw-cut regret) while SCR1 remains outside the primary six-case Context-OFF / Context-ON comparison.

---

## Paper-Reported Partition Results

The following table mirrors the partition-level result snapshot reported in the manuscript.

`R/S` denotes raw / scenario-sensitive crossing nets.

| Design | Scenario | Native R/S | Context-OFF R/S | Context-ON R/S | Context gain |
| --- | --- | ---: | ---: | ---: | ---: |
| PicoRV32 | control/datapath | 346 / 205 | 207 / 116 | 217 / 129 | -11.2% |
| PicoRV32 | memory-near-logic | 346 / 157 | 207 / 95 | 202 / 88 | +7.4% |
| PicoRV32 | state/clock | 346 / 211 | 207 / 98 | 214 / 90 | +8.2% |
| riscv32i | control/datapath | 230 / 119 | 229 / 126 | 241 / 116 | +7.9% |
| riscv32i | memory-near-logic | 230 / 104 | 229 / 105 | 226 / 96 | +8.6% |
| riscv32i | state/clock | 230 / 97 | 229 / 72 | 241 / 58 | +19.4% |

Context gain is the percentage reduction in scenario-sensitive crossings from Context-OFF to Context-ON. Positive values indicate fewer scenario-sensitive crossings after enabling recovered design context.

Across the six design-scenario pairs, Context-ON produces positive context gain in five cases. The PicoRV32 control/datapath case is retained as a negative case, demonstrating that the contribution of recovered design context is scenario dependent rather than universally beneficial.

The machine-readable version of this paper snapshot is available at:

```text
paper/table2_partition_results.csv
```

---

## Path-Level Validation

ASA-RV3D is additionally evaluated using an independent downstream proxy based on OpenSTA maximum-delay paths and fixed vertical-link delays of 20, 50, and 100 ps.

For PicoRV32, the evaluated path-level behavior is unchanged by refinement.

For riscv32i, Context-OFF and Context-ON both reduce the mean tier-transition count from **0.41 to 0.35** and the maximum observed transition count from **2 to 1**. The total negative slack degradation proxy is also lower than the native baseline under all evaluated vertical-delay assumptions.

The identical Context-OFF and Context-ON path-level results indicate that this path-continuity benefit comes from constrained refinement rather than from the additional design-context term.

The corresponding paper-facing data are stored at:

```text
paper/table3_path_validation.csv
```

The vertical-delay study is a validation proxy and is not a replacement for full post-refinement 3-D routing or signoff timing analysis.

---

## Repository Layout

```text
classifier/    Rule-based RISC-V design-context recovery.
configs/       Design and scenario configurations.
partition/     TritonPart-compatible refinement algorithms.
evaluation/    Metric extraction and evaluation scripts.
scripts/       Experiment and reproduction utilities.
results/       Generated and historical experiment artifacts.
docs/          Additional method notes and archived development documentation.
paper/         Frozen paper-facing tables and artifact manifest.
```

Historical files under `results/` and `docs/archive/` may contain intermediate algorithm variants or earlier terminology. For the final manuscript-facing method and result definitions, use this README, `docs/method.md`, and the files under `paper/`.

---

## Reproduction

The principal refinement implementation is:

```text
partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py
```

After the OpenROAD/OpenSTA features and the native timing-aware TritonPart assignment are available, a representative refinement run is:

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
  --output-dir results/picorv32_refinement/state_and_clock_protected
```

The paper-facing snapshot can be checked with:

```bash
python3 scripts/audit_paper_snapshot.py
```

Repository-level summaries and consistency checks can be refreshed using:

```bash
bash scripts/reproduce_core_results.sh
```

Large OpenROAD physical-design artifacts such as ODB, GDS, SPEF, and full run logs are not committed to the repository.

---

## Scope and Limitations

ASA-RV3D is an early-stage two-tier partition-refinement research prototype, not a complete 3-D physical-design implementation.

The repository does not claim:

- signoff 3-D placement and routing;
- explicit TSV or hybrid-bonding insertion;
- extracted post-3-D parasitics;
- thermal or IR-drop closure;
- final routed 3-D PPA.

The vertical-link-delay study and crossing metrics should therefore be interpreted as controlled partition-level and path-level proxies.

The design-context recovery is rule-based and explainable; it is not a trained machine-learning classifier.

---

## Paper Artifacts

The manuscript-facing snapshot is frozen under:

```text
paper/
```

See:

```text
paper/artifact_manifest.md
paper/table2_partition_results.csv
paper/table3_path_validation.csv
```

These files provide the explicit mapping between the public repository and the values reported in the manuscript.

---

## Citation

If you use ASA-RV3D in academic work, please cite the associated manuscript and repository:

```bibtex
@misc{duan2026asarv3d,
  author = {Hongyuan Duan},
  title  = {Constrained Post-Partition Refinement for RISC-V 3-D Tier Partitioning},
  year   = {2026},
  note   = {Manuscript and open-source implementation},
  url    = {https://github.com/Hongyuan-mees/ASA-RV3D}
}
```

Publication metadata will be updated after the paper is formally published.

---

## License

ASA-RV3D is released under the BSD 3-Clause License. See `LICENSE` for details.
