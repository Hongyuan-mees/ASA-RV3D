# Scenario Transfer Analysis

This note explains the scenario transfer experiment and the non-own-best cases.

The goal is to test whether scenario-aware partitioning is truly scenario-specific.  For each design and evaluation scenario, the experiment compares:

- generic balanced assignment,
- v3 graph-context assignment,
- assignment optimized for Control/Datapath split,
- assignment optimized for Memory-near-Logic,
- assignment optimized for State/Clock protected.

If the assignment optimized for the evaluated scenario is the best, the scenario objective is strongly scenario-specific.  If another scenario assignment wins, the result shows overlap between scenario objectives and deserves further analysis rather than being ignored.

## Summary

The transfer experiment shows that scenario-aware assignments consistently improve over v3_context and generic assignments.  However, the assignment optimized for the exact scenario is not always the absolute best.

| Design   | Evaluation scenario      | Best assignment              | Own assignment               | Own best? | Gap vs best |
| -------- | ------------------------ | ---------------------------- | ---------------------------- | --------- | ----------: |
| Ibex     | Control/Datapath split   | Control/Datapath split       | Control/Datapath split       | yes       |       0.00% |
| Ibex     | Memory-near-Logic        | Memory-near-Logic            | Memory-near-Logic            | yes       |       0.00% |
| Ibex     | State/Clock protected    | Control/Datapath split       | State/Clock protected        | no        |       0.42% |
| riscv32i | Control/Datapath split   | Memory-near-Logic            | Control/Datapath split       | no        |       0.45% |
| riscv32i | Memory-near-Logic        | Memory-near-Logic            | Memory-near-Logic            | yes       |       0.00% |
| riscv32i | State/Clock protected    | Memory-near-Logic            | State/Clock protected        | no        |       3.42% |

The non-own-best cases are small in two of the three cases.  The largest gap is riscv32i under the State/Clock protected scenario.

## Key Interpretation

The transfer failures are not caused by large-scale misplacement of architecture-critical units.  Most assignment differences are concentrated in generated control and generated datapath logic.

This suggests that, for these gate-level RISC-V designs, flexible generated logic can dominate the scenario objective.  Architecture-critical units such as clock/reset are visible and can influence the partition, but they may not be large enough to determine the global optimum by themselves, especially in smaller designs.

## Case 1: Ibex, State/Clock Protected

For Ibex under the State/Clock protected objective:

- best assignment: Control/Datapath split,
- own assignment: State/Clock protected,
- objective gap: 265.86,
- relative gap: 0.42%,
- own assignment has 435 more crossing-connection proxy count,
- own assignment also has slightly weaker instance and weight balance.

The tier-difference analysis shows:

| Architecture unit    | Changed instances | Share of changed instances |
| -------------------- | ----------------: | -------------------------: |
| generated_datapath   |               538 |                      43.8% |
| generated_control    |               528 |                      43.0% |
| clock_reset          |                92 |                       7.5% |
| register_file        |                31 |                       2.5% |

The State/Clock objective does affect clock/reset placement, but the final objective is still dominated by generated control/datapath crossing behavior.  Therefore, the Control/Datapath assignment can slightly outperform the State/Clock assignment under the State/Clock objective.

This is not a catastrophic failure.  The gap is less than 0.5%, and the result shows that the two scenario objectives have overlapping preferences for Ibex.

## Case 2: riscv32i, Control/Datapath Split

For riscv32i under the Control/Datapath objective:

- best assignment: Memory-near-Logic,
- own assignment: Control/Datapath split,
- objective gap: 40.71,
- relative gap: 0.45%,
- own assignment has only 12 more crossing-connection proxy count.

The tier-difference analysis shows:

| Architecture unit    | Changed instances | Share of changed instances |
| -------------------- | ----------------: | -------------------------: |
| generated_control    |                50 |                      72.5% |
| generated_datapath   |                10 |                      14.5% |
| clock_reset          |                 4 |                       5.8% |
| fetch                |                 4 |                       5.8% |

This case is essentially a near tie.  The difference is mostly from generated logic, not from a large disagreement about high-level architecture units.

## Case 3: riscv32i, State/Clock Protected

For riscv32i under the State/Clock protected objective:

- best assignment: Memory-near-Logic,
- own assignment: State/Clock protected,
- objective gap: 478.91,
- relative gap: 3.42%,
- own assignment has 123 more crossing-connection proxy count.

The tier-difference analysis shows:

| Architecture unit    | Changed instances | Share of changed instances |
| -------------------- | ----------------: | -------------------------: |
| generated_control    |               141 |                      73.4% |
| generated_datapath   |                49 |                      25.5% |
| execute_alu          |                 1 |                       0.5% |
| unclassified         |                 1 |                       0.5% |

Clock/reset does not appear among the changed units.  This means that the State/Clock objective did not induce a distinct clock/reset-driven partition for riscv32i.  The design is smaller than Ibex, and the objective remains dominated by generated control/datapath logic.

This is the strongest evidence that the State/Clock protected scenario needs either stronger weighting, richer clock-tree features, or physical clock-network information before it can become a clearly distinct scenario for small RISC-V designs.

## What This Means For The Project

The transfer test supports the main claim that scenario-aware partitioning is useful:

- scenario-aware assignments consistently improve over v3_context and generic assignments;
- the best assignment often matches the intended scenario;
- when it does not, the gap is explainable and mostly caused by generated logic dominance.

The test also gives an honest limitation:

- some current scenario objectives are not fully independent;
- State/Clock protected is weaker on riscv32i because clock/reset structure is too small or too coarsely modeled;
- future work should add clock-tree, timing, placement, or fanout-aware features to make this scenario more physically meaningful.

## Recommended Claim

Use this claim:

> Scenario-aware partitioning improves over generic and graph-context baselines across all evaluated scenarios.  Scenario transfer analysis shows that exact scenario-optimal assignments are often best and otherwise near-best; the remaining gaps are dominated by flexible generated logic rather than large-scale movement of architecture-critical units.

Avoid this claim:

> Every scenario always produces a uniquely optimal partition.

The second claim is not supported by the current data.

