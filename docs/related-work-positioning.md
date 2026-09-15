# Related Work Positioning

This note clarifies how ASA-RV3D should be positioned against existing 3D IC and RISC-V partitioning work.  Its purpose is to avoid overstating the contribution and to make the project defensible as an independent research prototype rather than a simplified reproduction of prior work.

## What This Project Should Not Claim

ASA-RV3D should not claim to be the first work on 3D IC tier partitioning.  Prior work already includes min-cut style methods, analytical/quadratic partitioning, FM-style refinement, and machine-learning based tier assignment.

ASA-RV3D should not claim to be the first work applying graph learning to 3D IC partitioning.  TP-GNN and related ML-based tier-partitioning work already use graph neural networks for monolithic 3D IC tier assignment, including processor-scale designs such as RocketCore and OpenPiton.

ASA-RV3D should not claim to be the first work studying RISC-V or SoC-level 3D integration.  Recent work has studied RISC-V SoC stacking scenarios such as Memory-on-Logic and Logic-on-Logic, including architectural modifications for low-latency memory access.

ASA-RV3D should not claim to produce signoff-quality 3D physical design.  The current implementation uses gate-level features and proxy costs; it does not perform full 3D placement, routing, timing closure, thermal analysis, or TSV/hybrid-bonding signoff.

## Closest Related Directions

### 1. General 3D IC Tier Partitioning

Traditional 3D IC partitioning focuses on assigning cells or blocks to tiers while balancing area and reducing inter-tier connections.  Some flows repurpose 2D place-and-route tools and add a tier-partitioning stage before implementation.  Examples include min-cut style partitioning and analytical quadratic partitioning.

Difference from ASA-RV3D:

ASA-RV3D does not compete as a full physical-design flow.  It focuses on an earlier design-space exploration layer: mapping gate-level cells back to RISC-V architectural roles and evaluating how different 3D integration scenarios change partitioning behavior.

### 2. ML/GNN-Based Tier Partitioning

TP-GNN and later ML-powered methodologies use graph representation learning to generate tier assignments for monolithic 3D ICs.  These approaches directly target partition quality and downstream physical-design QoR.

Difference from ASA-RV3D:

ASA-RV3D is not primarily a GNN replacement.  Its graph-context component is a lightweight confidence signal, not a full learned tier partitioner.  The core contribution is explainable architecture/scenario conditioning: RISC-V unit mapping, scenario-specific cost models, and scenario transfer analysis.

### 3. RISC-V / SoC 3D Integration Studies

Recent RISC-V SoC studies examine 3D stacking scenarios such as Memory-on-Logic and Logic-on-Logic, sometimes with architectural modifications to reduce communication latency and improve PPA.

Difference from ASA-RV3D:

ASA-RV3D does not claim signoff PPA results.  Instead, it provides a public, lightweight, reproducible gate-level experiment that asks how RISC-V architectural semantics can guide early tier-assignment decisions before expensive physical implementation.

## Actual Contribution of ASA-RV3D

The defensible contribution is:

ASA-RV3D is a lightweight, explainable, open-source framework for RISC-V gate-level architecture-to-3D-scenario partition exploration.

More specifically, the project contributes:

1. A public ORFS/OpenROAD-based experimental pipeline for RISC-V gate-level benchmarks.
2. A gate-level-to-architecture mapping layer that assigns instances to RISC-V-related architecture units such as fetch, CSR, register file, datapath, clock/reset, and generated logic.
3. Scenario-specific 3D proxy cost models for integration choices such as Memory-near-Logic, Control/Datapath split, and State/Clock protected partitioning.
4. Scenario-aware tier assignment that optimizes a scenario-specific objective rather than only generic crossing count.
5. Scenario transfer tests showing whether a partition optimized for one 3D scenario remains good under another scenario.
6. Explainable result tables and heatmaps that identify which architecture units dominate crossing behavior under each scenario.

## How To Phrase The Innovation

Preferred wording:

> ASA-RV3D introduces an explainable RISC-V architecture-aware and scenario-aware tier-partition exploration flow.  It maps gate-level instances to architecture units, evaluates scenario-specific 3D proxy costs, and compares generic, graph-context, and scenario-aware assignments across public RISC-V benchmarks.

Avoid:

> We propose the first RISC-V 3D partitioning algorithm.

Avoid:

> We outperform GNN-based 3D partitioning.

Avoid:

> This is a full 3D physical design tool.

## Why The Project Is Still Meaningful

The project is meaningful because many advanced 3D partitioning methods are either closed, require heavy physical-design infrastructure, or focus on generic netlist/placement features.  ASA-RV3D explores a different niche: low-cost, reproducible, architecture-informed early-stage analysis for RISC-V designs.

The value is not that the heuristic is mathematically stronger than state-of-the-art GNN methods.  The value is that the framework makes RISC-V architectural intent visible at gate level and connects it to 3D integration scenarios in a way that is easy to inspect, reproduce, and extend.

## Current Evidence In This Repository

Current results support the following limited claims:

- Scenario-aware partitioning improves over generic balance and v3 graph-context assignments under the scenario proxy objectives.
- Scenario transfer experiments show that scenario-specific assignments often perform best or near-best under their intended scenario.
- Architecture-unit heatmaps reveal which RISC-V-related units dominate crossing behavior under each scenario.
- The method is explainable: the reason for a move or cost increase can be traced to architecture unit, graph context, scenario weight, and crossing behavior.

Current results do not yet support:

- signoff PPA improvement,
- timing closure improvement,
- thermal improvement,
- true TSV/hybrid-bond count reduction,
- superiority over TP-GNN or industrial partitioners.

## Recommended Next Experiments

To strengthen the project, the next experiments should focus on:

1. More RISC-V benchmarks if runtime allows.
2. Stronger connectivity-only and FM-style baselines under the same scenario objectives.
3. Sensitivity analysis for scenario weights to show robustness.
4. Physical proxy enrichment using placement, estimated wirelength, or timing reports.
5. A small learned scorer or GNN-inspired feature module, used as an optional extension rather than the central claim.

## References To Cite

- TP-GNN / ML-powered tier partitioning for monolithic 3D ICs.
- 3D partitioning and pipeline optimization for low-latency memory access in RISC-V many-core SoCs.
- Multi-tier 3D IC physical design using analytical/quadratic partitioning and 2D P&R tools.
- Gate-level clustering and automated 3D IC system partitioning discussions.

