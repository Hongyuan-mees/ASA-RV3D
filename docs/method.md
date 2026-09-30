# ASA-RV3D Method

This document describes the paper-facing ASA-RV3D method used by the public artifact. Historical development notes and older algorithm variants are archived under `docs/archive/`.

## Problem Setting

ASA-RV3D operates on a two-tier gate-level partitioning problem. Given a synthesized RISC-V design and a native timing-aware TritonPart assignment, the method performs constrained local refinement over individual instance tier assignments.

The goal is not to replace TritonPart or to minimize raw cut count alone. Instead, ASA-RV3D asks whether a strong native timing-aware partition can be locally refined using physical, timing, and optional recovered design-context information while preserving explicit feasibility constraints.

## High-Level Flow

```text
Native timing-aware TritonPart assignment
        |
        v
Gate-level, physical, and timing artifacts
        |
        v
Normalized instance-level refinement weights
        |
        v
Risk-weighted candidate move evaluation
        |
        v
Area / raw-cut / timing-path feasibility guards
        |
        v
Greedy constrained local refinement
        |
        v
Refined two-tier assignment
```

## Context Components

ASA-RV3D combines three normalized context components:

- **Physical context** derived from OpenROAD artifacts and instance-level physical evidence.
- **Timing context** derived from OpenSTA/OpenROAD timing information.
- **Recovered design context** derived from explainable rule-based mapping of synthesized instances back to coarse RISC-V functional roles and semantic groups.

The recovered design context is optional guidance. It is not a hard architectural placement constraint and does not force complete functional blocks onto one tier.

## Context-OFF and Context-ON

The paper uses two controlled configurations:

- **Context-OFF** keeps the physical and timing components while disabling recovered design context.
- **Context-ON** enables physical, timing, and recovered design-context components under the same feasibility guards.

This comparison isolates the effect of recovered design context on scenario-sensitive crossing metrics.

## Refinement Objective and Feasibility Guards

Candidate moves are ranked by a normalized risk-weighted objective. Feasibility is checked separately.

A move is admitted only if it respects the paper configuration:

- reconstructed tier-0 area fraction between `0.48` and `0.52`;
- maximum raw-crossing regret of `5%` relative to the native timing-aware baseline;
- up to `100` OpenSTA maximum-delay paths;
- mean tier-transition regret limit of `0`;
- worst tier-transition increase limit of `0`;
- maximum refinement budget of `300` iterations;
- convergence window of `10` accepted moves;
- minimum recent relative gain of `1e-3`.

This separation is important: the objective ranks legal candidate moves, while the guards preserve baseline area, raw-cut, and timing-path properties.

## Algorithm Sketch

```text
Input:
  A0: native timing-aware TritonPart assignment
  F: gate-level, physical, and timing features
  D: optional recovered design context
  S: design-context scenario
  G: feasibility guards

Output:
  A*: refined two-tier assignment

1. Set A <- A0.
2. Normalize physical, timing, and optional design-context weights.
3. Compute baseline raw-crossing and timing-path guard metrics.
4. Repeat until convergence, no legal move, or the move budget is reached:
   a. Enumerate candidate single-instance tier moves.
   b. Estimate objective gain for each candidate.
   c. Reject candidates that violate area, raw-cut, or timing-path guards.
   d. Accept the best remaining improving move.
   e. Update the current assignment and incremental metrics.
5. Return A* and write the assignment, summary, and trace artifacts.
```

## Paper-Facing Result Source

The manuscript-facing result snapshot is stored under `paper/`:

- `paper/table2_partition_results.csv` records the partition-level Context-OFF / Context-ON comparison.
- `paper/table3_path_validation.csv` records the downstream path-level validation snapshot.
- `paper/artifact_manifest.md` documents provenance and scope.

Generated outputs under `results/` are retained as historical and development artifacts. They may include earlier terminology or intermediate method variants and should not be used as the final manuscript source of truth unless explicitly referenced by `paper/`.

## Scope

ASA-RV3D is an early-stage partition-refinement prototype. It does not claim signoff-quality 3-D placement, routing, TSV or hybrid-bonding insertion, extracted 3-D parasitics, thermal closure, IR-drop closure, or final routed PPA.
