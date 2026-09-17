# ASA-RV3D Method

ASA-RV3D stands for Architecture-Semantic-Aware RISC-V 3D Partitioning.

It is a research prototype for early 2-tier assignment of RISC-V gate-level designs. The method does not replace a full 3D physical design flow. Its purpose is narrower and more practical: use lightweight netlist evidence to decide whether architecture-aware tier assignment can reduce inter-tier communication while keeping the two tiers reasonably balanced.

## Current Mainline Algorithm

The current ASA-RV3D algorithm is a timing-regret guarded repair layer over a strong TritonPart initial partition.

It should be understood as:

```text
TritonPart connectivity-first partition
+ RISC-V architecture semantic recovery
+ 3D scenario-aware cost
+ coverage-gated physical context
+ OpenSTA/OpenROAD timing-context guard
= ASA-RV3D timing-regret guarded repair
ASA-RV3D does not claim raw-cut superiority over TritonPart. TritonPart supplies the strong hypergraph partition. ASA-RV3D then performs small guarded local moves when they improve architecture/scenario/physical objectives without unacceptable timing-regret or balance degradation.
The repaired objective is evaluated as:
scenario_objective
+ physical_weight * physical_context_crossing_penalty
+ timing_weight * timing_context_crossing_penalty
with guardrails:
instance_balance >= effective_instance_balance_floor
weight_balance   >= effective_weight_balance_floor
timing_regret    <= allowed_timing_regret_per_move
The balance floor is adaptive. If the TritonPart initial assignment already satisfies the requested floor, ASA-RV3D preserves that floor. If the initial assignment is below the requested floor, ASA-RV3D prevents further degradation instead of forcing an unrealistic correction.
In plain words: TritonPart cuts the graph well; ASA-RV3D makes the cut more aware of RISC-V architecture, 3D scenario intent, physical risk, and timing-sensitive crossings.
## Algorithm 1: Timing-Regret Guarded Repair

```text
Input:
  H(V, E): gate-level hypergraph
  A0: TritonPart initial two-tier assignment
  U(v): architecture unit of instance v
  Cg(v): graph-context confidence
  Cp(v): coverage-gated physical-context score
  Ct(v): timing-context score from OpenSTA/OpenROAD reports
  S: selected 3D integration scenario
  Binst, Bweight: requested balance floors
  Rmax: maximum allowed timing-regret per move

Output:
  A*: repaired two-tier assignment

1. Set A <- A0.
2. Compute effective balance floors:
     if A0 already satisfies Binst/Bweight:
         preserve requested floors
     else:
         prevent further balance degradation from A0.
3. Build net-level scenario, physical, and timing crossing risks.
4. Evaluate the initial guarded objective:
     objective(A) =
       scenario_objective(A)
       + physical_weight * physical_crossing_penalty(A)
       + timing_weight * timing_crossing_penalty(A)
5. Repeat local refinement passes:
     a. Enumerate candidate single-instance moves v -> opposite tier.
     b. For each move, estimate:
          scenario gain,
          physical penalty change,
          timing-regret,
          instance balance after move,
          weight balance after move.
     c. Reject the move if it violates effective balance floors.
     d. Reject the move if timing-regret > Rmax.
     e. Accept the best remaining move only if it improves the guarded objective.
6. Stop when no legal improving move remains or the move budget is reached.
7. Return A* and write the assignment, comparison table, and refinement trace.
This algorithm is intentionally conservative. It treats TritonPart as the strong connectivity baseline, then allows ASA-RV3D to make only those local changes that improve architecture/scenario/physical objectives without unacceptable timing-regret or balance damage.
## Problem Setting

Given a gate-level netlist produced by ORFS/OpenROAD, assign each instance to one of two tiers:

```text
tier0 or tier1
```

The assignment should:

- reduce inter-tier crossing connections,
- keep tier sizes balanced,
- keep proxy-weight balance acceptable,
- preserve useful RISC-V architecture structure where it helps.

The current metric, `crossing_connections_proxy`, is a lightweight communication proxy. It is not a true TSV count.

## Motivation

Generic partitioning sees the circuit mostly as a graph. That is useful, but it misses an important fact: a processor netlist is not just random logic. Even after synthesis, the design still contains traces of architecture-level structure, such as control logic, datapath logic, pipeline state, register state, clock/reset logic, fetch logic, and execute logic.

ASA-RV3D uses those traces as soft guidance. It does not force an entire architectural block onto one tier. Instead, it asks a more flexible question:

> If the netlist still contains architecture semantics, can those semantics help guide a better tier assignment?

## Method Overview

The current flow has six stages:

```text
1. ORFS/OpenROAD baseline generation
2. Gate-level feature extraction
3. Architecture semantic recovery
4. Graph-context semantic scoring
5. Architecture-aware tier partitioning
6. Multi-metric evaluation and visualization
```

## Stage 1: ORFS/OpenROAD Baseline

The project starts from public ORFS/OpenROAD flows on sky130hd. The current benchmarks are:

| Design | Platform | Route DRC Lines | Status |
| --- | --- | ---: | --- |
| Ibex | sky130hd | 0 | clean baseline |
| riscv32i | sky130hd | 0 | clean baseline |

Large physical artifacts such as ODB, DEF, GDS, SPEF, and full logs are kept outside the Git repository. The repository stores compact summaries and reproducible derived data.

## Stage 2: Gate-Level Feature Extraction

`scripts/extract_orfs_baseline.py` reads the final gate-level Verilog and selected ORFS reports, then writes compact CSV/JSON features.

Typical outputs include:

- `instance_features.csv`
- `net_summary.csv`
- `cell_type_summary.csv`
- `module_summary.csv`
- `manifest.json`

These files are small enough to version-control and make later experiments reproducible.

## Stage 3: Architecture Semantic Recovery

`classifier/architecture_classifier.py` assigns each instance to an architecture-related class.

Examples include:

```text
generated_control
generated_datapath
pipeline_state
register_file
clock_reset
csr
fetch
load_store
execute_alu
multdiv
trap_debug
unclassified
```

This classifier is deliberately simple and explainable. It uses name patterns, cell categories, and structural hints from the extracted features. This is not claimed as a novel machine-learning classifier. Its purpose is to recover a transparent semantic signal that can be used by the partitioner.

## Stage 4: Graph-Context Semantic Scoring

`evaluation/graph_context_score.py` adds a graph-neighborhood confidence signal.

The key idea is simple:

- If an instance is labeled as control logic and most of its netlist neighborhood also looks control-like, the label is more trustworthy.
- If an instance is labeled as datapath logic but its neighborhood is mixed or weak, the partitioner should trust the label less.

The script computes two main scores:

```text
semantic_context_score
boundary_likelihood_score
```

`semantic_context_score` estimates how strongly an instance's graph neighborhood supports its semantic group.

`boundary_likelihood_score` estimates whether an instance sits near semantic boundaries, where crossing decisions may matter more.

This stage is important because it moves the project beyond pure name-based classification. The classifier proposes a semantic label; the graph-context scorer checks whether the local connectivity structure supports that label.

## Historical Standalone Partitioning Variants

These older variants are retained as ablations. They are no longer the mainline claim.

### Generic Balance

This baseline balances instances and proxy weights without using architecture semantics. It is useful as a lower bar: if architecture-aware methods cannot beat it, the semantic guidance is not helping.

### Architecture-Aware V1

This version creates a direct architecture-guided tier assignment. It often reduces crossing, but it can be badly imbalanced. For example, on riscv32i, v1 reduces crossing but produces poor tier balance.

V1 is therefore best understood as a semantic starting point, not as a final algorithm.

### Architecture-Score V2

`partition/partition_v2.py` adds balance-aware local refinement.

It uses a greedy FM-style move process. Each candidate move sends one instance from its current tier to the other tier. The move is accepted if it improves the objective and respects balance, or if it monotonically repairs an infeasible balance state.

The v2 objective is:

```text
crossing proxy
+ instance balance penalty
+ proxy-weight balance penalty
+ architecture placement penalty
```

This is the first strong version of the method. It keeps the architecture signal, but avoids the main weakness of v1: poor balance.

### Graph-Context V3

`partition/partition_v3_context.py` adds graph-context confidence to the architecture penalty.

The v3 idea is:

```text
trust architecture preference more
when graph context strongly supports the semantic label
```

and:

```text
let crossing and balance dominate
when graph context is weak
```

This creates a lightweight graph-aware version of ASA-RV3D without training a GNN.

## Local Refinement Logic

The algorithm is FM-style because it improves a partition through local instance moves and gain evaluation. It is not a full implementation of the original Fiduccia-Mattheyses algorithm. It does not use the full bucket gain data structure, lock/unlock policy, or rollback scheme.

A precise description is:

> ASA-RV3D uses greedy FM-style local refinement with architecture-semantic penalties, graph-context confidence, and monotonic balance repair.

## Pseudocode

```text
Input:
  gate-level instance features
  net connectivity summary
  architecture class per instance
  optional graph-context score per instance
  balance thresholds

Output:
  tier assignment

1. Build net-to-instance connectivity.
2. Assign each instance a semantic group.
3. Build an architecture-aware initial assignment.
4. Compute initial crossing and balance metrics.
5. For each refinement pass:
     for each candidate instance:
       propose moving the instance to the other tier
       estimate crossing change
       estimate balance change
       estimate architecture penalty change
       if using v3:
         scale architecture penalty by graph-context confidence

       accept the move if:
         objective improves and balance is feasible
         or current balance is infeasible and the move repairs balance

6. Write assignment, comparison table, class distribution, trace, and manifest.
```

## What Is New

The novelty is not that graph partitioning exists. It obviously does. The novelty is the specific integration for RISC-V tier assignment:

1. Recover architecture-related semantics from public gate-level ORFS outputs.
2. Use those semantics as soft tiering preferences rather than hard module cuts.
3. Add balance-repair local refinement so useful but imbalanced semantic partitions become feasible.
4. Add graph-context confidence so architecture guidance is stronger only when the netlist neighborhood supports it.
5. Evaluate the method with generic, architecture-only, connectivity-only, ablation, and graph-context baselines.

This makes the project more than a toy classifier. The semantic labels become active optimization signals, and the experiments test whether those signals actually improve partition quality.

## Current Evidence

### V2 Main Results

| Design | Generic Crossing | V2 Crossing | Reduction |
| --- | ---: | ---: | ---: |
| Ibex | 18943 | 8585 | 54.7% |
| riscv32i | 6422 | 1791 | 72.1% |

### Connectivity-Only Comparison

| Design | Connectivity-Only Crossing | Full V2 Crossing | Full V2 Effect |
| --- | ---: | ---: | --- |
| Ibex | 13842 | 8585 | lower crossing with architecture terms |
| riscv32i | 2766 | 1791 | lower crossing with architecture terms |

### V3 Graph-Context Results

| Design | V2 Crossing | V3 Context Crossing | V3 Effect |
| --- | ---: | ---: | --- |
| Ibex | 8585 | 7410 | 13.7% lower crossing than v2 |
| riscv32i | 1791 | 1800 | similar crossing with better balance |

The current evidence suggests that architecture semantics help, and graph-context confidence can further improve or stabilize the result.

## Honest Limitations

- The crossing metric is a proxy, not a physical TSV count.
- The project does not perform full 3D placement and routing.
- The semantic classifier is rule-based.
- Graph-context scoring is not a trained GNN.
- The current benchmark set has two RISC-V designs.
- The algorithm is a prototype, not a production EDA solver.

## Next Improvements

The most valuable next steps are:

1. Add more RISC-V benchmarks.
2. Add random-seed and stronger connectivity-only baselines.
3. Improve semantic classification with hierarchy-aware features.
4. Add optional GNN-assisted scoring, using the current graph-context score as a stepping stone.
5. Add physical-aware proxies such as estimated wirelength and crossing locality.
6. Connect tier assignment to a downstream 3D floorplanning or placement experiment.
