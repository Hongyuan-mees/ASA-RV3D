# RISC-V-Aware 3D Proxy Cost Model

This document defines the lightweight 3D proxy cost model used in ASA-RV3D.

The goal is not to replace full 3D physical design signoff. Instead, the model provides an interpretable early-stage metric for comparing tier assignments before detailed 3D placement, routing, timing, power, and thermal analysis are available.

## Motivation

Counting inter-tier crossings is useful but incomplete.

In a RISC-V processor, not all crossing connections are equally important. A crossing net related to clock/reset, register-file access, pipeline state, or datapath movement may be more costly than a crossing net inside generic glue logic. Similarly, a high-fanout crossing may be more expensive than a small local crossing.

The RISC-V-aware 3D proxy cost model asks:

> Which architecture-relevant nets cross tiers, and how expensive do those crossings look under an interpretable 3D proxy model?

This moves the evaluation from simple crossing count toward architecture-aware 3D partition planning.

## Inputs

The evaluator reads:

```text
instance_features.csv
architecture_instance_classes.csv
graph_context_scores.csv
assignment.csv
```

These files provide:

- instance-to-net connectivity,
- architecture class per instance,
- semantic group per instance,
- graph-context confidence,
- tier assignment.

## Cost Terms

For each crossing net, the model computes:

```text
3D proxy cost =
  base crossing cost
+ high-fanout cost
+ control/datapath boundary cost
+ architecture criticality cost
+ semantic uncertainty cost
```

The total design-level score is the sum over all crossing nets.

## Base Crossing Cost

The base crossing cost measures the ordinary crossing proxy:

```text
base_crossing_cost = crossing_connections_proxy
```

This keeps the metric connected to the earlier crossing-count experiments.

## High-Fanout Cost

High-fanout crossing nets are penalized more heavily:

```text
high_fanout_cost = crossing_proxy * max(0, net_fanout - 8) * high_fanout_weight
```

The intuition is that a high-fanout signal crossing tiers may create more routing, buffering, bonding, or synchronization pressure than a small local net.

## Control/Datapath Boundary Cost

If a crossing net connects both control-like and datapath-like logic, the model adds a boundary penalty:

```text
control_datapath_boundary_cost = crossing_proxy * boundary_weight
```

This captures the idea that control/datapath boundaries are architecturally meaningful. Excessive crossings across this boundary may indicate a less clean 3D split.

## Architecture Criticality Cost

Each architecture class receives a lightweight criticality weight.

Examples:

| Architecture Class | Weight | Rationale |
| --- | ---: | --- |
| `clock_reset` | 5.0 | Clock/reset crossing should be minimized. |
| `register_file` | 4.0 | Register-file access can be port- and timing-sensitive. |
| `load_store` | 3.5 | Load/store paths relate to memory access. |
| `pipeline_state` | 3.0 | Pipeline state affects sequential boundaries. |
| `csr` | 2.5 | CSR state affects privileged/control behavior. |
| `execute_alu`, `multdiv` | 2.0 | Datapath execution logic can be timing-sensitive. |
| `generated_datapath` | 1.5 | Generic datapath-like logic. |
| `generated_control` | 1.2 | Generic control-like logic. |
| `unclassified` | 1.0 | Unknown or weak semantic evidence. |

For a crossing net, the model uses the maximum architecture-class weight among connected instances.

This is intentionally conservative: if any part of a crossing net touches a critical architecture class, the crossing becomes more expensive.

## Semantic Uncertainty Cost

The model also uses graph-context confidence:

```text
semantic_uncertainty_cost =
  crossing_proxy * (1 - mean_semantic_context_score) * uncertainty_weight
```

If the semantic labels around a crossing net are weak or inconsistent, the cost increases. This discourages over-trusting architecture labels in ambiguous graph regions.

## Why This Is Better Than Crossing Count Alone

The earlier metric only asked:

```text
How many connections cross tiers?
```

The 3D proxy model asks:

```text
Which RISC-V architecture-relevant connections cross tiers?
How large are they?
Do they touch critical structures?
Are the semantics locally reliable?
```

This is closer to the real 3D partitioning problem, where a crossing's cost depends on what kind of signal it is and where it appears in the architecture.

## Current Results

The current summary is stored at:

```text
results/benchmark_summary/riscv_3d_proxy_cost_summary.csv
```

The main result figure is:

```text
results/figures/summary/riscv_3d_proxy_cost_summary.svg
```

### Ibex

| Method | 3D Proxy Cost | Reduction vs Generic |
| --- | ---: | ---: |
| Generic balance | 128244.7 | 0.0% |
| Connectivity-only | 90502.3 | 29.4% |
| ASA-RV3D v2 | 57108.8 | 55.5% |
| ASA-RV3D v3 context | 49429.8 | 61.5% |

### riscv32i

| Method | 3D Proxy Cost | Reduction vs Generic |
| --- | ---: | ---: |
| Generic balance | 42816.1 | 0.0% |
| Connectivity-only | 17375.5 | 59.4% |
| ASA-RV3D v2 | 12712.0 | 70.3% |
| ASA-RV3D v3 context | 11996.8 | 72.0% |

## Interpretation

The result strengthens the ASA-RV3D argument.

The project no longer only claims that architecture-aware partitioning reduces raw crossing count. It also shows that the method reduces architecture-weighted 3D proxy cost.

The strongest current observation is:

> Graph-context v3 gives the lowest RISC-V-aware 3D proxy cost on both tested designs.

This suggests that graph-context confidence helps the partitioner avoid more expensive crossing structures, not just fewer crossings.

## Limitations

This model is still a proxy.

It does not compute:

- true TSV count,
- hybrid-bonding site demand,
- post-3D-placement wirelength,
- timing slack,
- power,
- thermal behavior,
- routing congestion.

The weights are interpretable heuristic weights, not calibrated physical constants. The next step should include sensitivity analysis and, eventually, connection to placement or floorplanning data.

## Recommended Next Steps

1. Run sensitivity analysis over the cost weights.
2. Report top expensive crossing nets per design.
3. Add physical locality or estimated wirelength if placement coordinates become available.
4. Use this proxy cost as an objective term in a future `partition_v4`.
5. Compare against additional RISC-V benchmarks.
