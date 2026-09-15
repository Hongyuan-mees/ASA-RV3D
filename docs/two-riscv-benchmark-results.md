# Two RISC-V Benchmark Results

This document summarizes the current two-design RISC-V evaluation.

## Benchmarks

| Design | Platform | Instances | Route DRC Lines | Status |
| --- | --- | ---: | ---: | --- |
| Ibex | sky130hd | 15601 | 0 | clean baseline |
| riscv32i | sky130hd | 5737 | 0 | clean baseline |

## Main Partition Results

| Design | Method | Crossing Proxy | Reduction vs Generic | Instance Balance | Weight Balance |
| --- | --- | ---: | ---: | ---: | ---: |
| Ibex | Generic balance | 18943 | 0.0% | 0.999872 | 0.999946 |
| Ibex | Architecture-aware v1 | 13843 | 26.9% | 0.821483 | 0.999946 |
| Ibex | Architecture-score v2 | 8585 | 54.7% | 0.906281 | 0.958692 |
| riscv32i | Generic balance | 6422 | 0.0% | 0.999651 | 0.999859 |
| riscv32i | Architecture-aware v1 | 3859 | 39.9% | 0.543449 | 0.613791 |
| riscv32i | Architecture-score v2 | 1791 | 72.1% | 0.970800 | 0.989585 |

## riscv32i Ablation

| Case | Crossing Proxy | Instance Balance | Weight Balance | Tier0 Top Class | Tier1 Top Class |
| --- | ---: | ---: | ---: | --- | --- |
| Full v2 | 1791 | 0.970800 | 0.989585 | generated_control | generated_datapath |
| No architecture penalty | 1783 | 0.981008 | 0.982192 | generated_control | generated_control |
| No balance penalty | 2050 | 0.831737 | 0.822471 | generated_control | generated_datapath |

## Interpretation

The architecture-score v2 heuristic reduces crossing proxy on both RISC-V benchmarks while maintaining usable tier balance.

On riscv32i, the no-architecture-penalty variant achieves a slightly lower crossing proxy, but it loses the architecture-oriented tier separation: both tiers are dominated by generated_control. This suggests that architecture penalty should be interpreted as a semantic-structure preservation term, not merely as a crossing minimization term.

The no-balance-penalty variant performs worse on both crossing and balance for riscv32i, indicating that balance-aware repair is useful for guiding local refinement out of a highly imbalanced architecture-aware initial assignment.
