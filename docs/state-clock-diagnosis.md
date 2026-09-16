# State/Clock Structural Diagnosis

This note explains why the State/Clock protected scenario is weaker than expected in some scenario-transfer cases.

The purpose of this diagnosis is not to tune weights until the desired result appears.  Instead, it checks whether clock/reset and state-related units are structurally strong enough in the current gate-level proxy data to justify a distinct State/Clock protected scenario.

## Question

The scenario transfer experiment showed that the State/Clock protected assignment is not always the best assignment under the State/Clock protected objective.

This raises an important question:

Is this a partitioning algorithm failure, or is the current State/Clock scenario definition missing important physical structure?

## Diagnosis Method

The diagnosis examines:

- fraction of instances mapped to state/clock-related units,
- fraction of net pin incidence involving those units,
- fraction of crossing nets touching those units,
- fraction of crossing-connection proxy involving those units,
- which architecture units dominate crossing behavior.

State/clock-related units are defined as:

- `clock_reset`
- `pipeline_state`
- `register_file`
- `csr`
- `trap_debug`

## Summary Results

| Design   | State/clock instance fraction | State/clock net-pin fraction | State/clock crossing-net fraction | State/clock crossing-connection fraction |
| -------- | ----------------------------: | ---------------------------: | --------------------------------: | ---------------------------------------: |
| Ibex     |                         15.8% |                        14.7% |                             33.2% |                                    27.7% |
| riscv32i |                         19.7% |                        18.8% |                             19.4% |                                    19.5% |

## Interpretation

### Ibex

Ibex has a meaningful state/clock structural signal.

Although state/clock-related units represent only 15.8% of instances and 14.7% of net-pin incidence, they touch 33.2% of crossing nets and contribute 27.7% of crossing-connection proxy under the State/Clock protected assignment.

This means the State/Clock scenario is not empty for Ibex.  The partitioning flow does see state/clock-related structure.  However, the global objective is still strongly affected by generated control and generated datapath logic.

The dominant crossing units are:

| Unit               | Crossing nets |
| ------------------ | ------------: |
| generated_control  |          4515 |
| generated_datapath |          3784 |
| register_file      |          1299 |
| csr                |           306 |
| clock_reset        |           163 |
| pipeline_state     |           122 |

The `register_file` and `csr` units provide meaningful state-related signal.  However, `clock_reset` itself contributes relatively few crossing nets.  Therefore, the State/Clock protected objective can be influenced by state-related units, but it is still dominated by generated logic.

This explains why the Control/Datapath assignment can slightly outperform the State/Clock assignment under the Ibex State/Clock objective.  The gap is small, and the difference is mainly caused by generated logic and balance effects rather than a complete failure to protect state/clock structure.

### riscv32i

riscv32i has a much weaker state/clock structural signal.

State/clock-related units represent 19.7% of instances and 18.8% of net-pin incidence, but they contribute only 19.4% of crossing nets and 19.5% of crossing-connection proxy.  In other words, their crossing contribution is roughly proportional to their size; they do not dominate the crossing structure.

The dominant crossing units are:

| Unit               | Crossing nets |
| ------------------ | ------------: |
| generated_control  |          1473 |
| generated_datapath |          1108 |
| pipeline_state     |           302 |
| execute_alu        |           275 |
| unclassified       |           188 |
| clock_reset        |            12 |

The key observation is that `clock_reset` contributes only 12 crossing nets.  This is too small to drive a distinct State/Clock protected optimum in the current proxy model.

Therefore, the riscv32i State/Clock protected result should not be interpreted as a simple algorithm failure.  The current feature set does not contain enough clock-tree, timing, or placement structure for the State/Clock scenario to become strongly distinct.

## Why Simple Weight Tuning Is Not Enough

Increasing the `clock_reset` multiplier might make the State/Clock assignment win, but that would be a weak scientific argument if the underlying structure is not present.

The diagnosis suggests that the root issue is feature incompleteness, not merely insufficient weight.  The current gate-level proxy captures instance classes and net connectivity, but it does not capture:

- clock-tree topology,
- clock sink distribution,
- reset fanout structure,
- sequential clustering,
- pipeline-stage locality,
- timing criticality,
- placement distance,
- physical clock-network constraints.

Without these features, a State/Clock protected scenario can only be partially represented.

## Project-Level Conclusion

The State/Clock protected scenario is structurally meaningful for Ibex but weak for riscv32i.

In both designs, crossing behavior is dominated by generated control/datapath logic.  State-related units such as `register_file`, `csr`, and `pipeline_state` can matter, but `clock_reset` itself contributes little crossing, especially in riscv32i.

Therefore:

- The project should not force State/Clock protected to always win by manually increasing weights.
- The current results should be presented as a diagnostic finding.
- Later stages enriched the model with coverage-gated physical context and OpenSTA timing-regret guards. The result is still a proxy-level repair study, not a signoff timing-closure claim.

## Recommended Claim

Use this claim:

> The State/Clock protected scenario reveals a limitation of purely gate-level connectivity proxies.  Ibex contains visible state-related crossing structure, but riscv32i does not exhibit strong clock/reset crossing under the current feature set.  This indicates that robust state/clock-aware 3D partitioning requires richer clock-tree, timing, or placement features rather than simple weight tuning.

Avoid this claim:

> State/Clock protected partitioning is solved by increasing clock/reset weights.

The current data does not justify that claim.

