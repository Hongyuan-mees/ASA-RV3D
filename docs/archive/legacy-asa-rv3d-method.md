# Legacy ASA-RV3D Method Narrative

This document is preserved as historical development documentation. It predates the paper-facing ASA-RV3D artifact and may use older terminology such as architecture-aware, Phase-3, V1/V2/V3, or architecture semantics.

For the current paper-facing method description, use `docs/method.md`, the top-level `README.md`, and the frozen `paper/` artifacts.

---

# ASA-RV3D Method

ASA-RV3D stands for Architecture-Semantic-Aware RISC-V 3D Partitioning.

It is a research prototype for early 2-tier assignment of RISC-V gate-level designs. The method does not replace a full 3D physical design flow. Its purpose is narrower and more practical: use lightweight netlist evidence to decide whether architecture-aware tier assignment can reduce inter-tier communication while keeping the two tiers reasonably balanced.

## Current Mainline Algorithm

The current ASA-RV3D algorithm is a timing-aware repair layer over a strong TritonPart initial partition.

It should be understood as:

```text
TritonPart connectivity-first partition
+ RISC-V architecture semantic recovery
+ 3D scenario-aware cost
+ coverage-gated physical context
+ OpenSTA/OpenROAD timing-context guard
= ASA-RV3D final tier assignment
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
## Algorithm 1: ASA-RV3D

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

This archived file intentionally preserves an older partial method narrative. It is no longer the paper-facing source of truth.
