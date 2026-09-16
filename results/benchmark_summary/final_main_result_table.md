# Final Main Result Table

Timing-weighted crossing comparison for TritonPart, ASA-RV3D guarded repair, and timing-regret guarded repair.

| Design | Scenario | TritonPart | Guarded Repair | Timing-Regret Guarded | Reduction vs Guarded | Reduction vs TritonPart | Crossing Nets Change | High-Timing Crossing Nets Change |
| ------ | -------- | ---------: | -------------: | --------------------: | -------------------: | ----------------------: | -------------------: | -------------------------------: |
| riscv32i | Control/datapath | 11.439099 | 11.747528 | 11.336352 | 3.50% | 0.90% | +0 | +0 |
| riscv32i | Memory-near-logic | 11.439099 | 11.462790 | 11.336352 | 1.10% | 0.90% | -12 | +0 |
| riscv32i | State/clock protected | 11.439099 | 12.377965 | 11.356957 | 8.25% | 0.72% | -8 | -1 |
| Ibex | Control/datapath | 19.145480 | 20.285616 | 17.841802 | 12.05% | 6.81% | -2 | -1 |
| Ibex | Memory-near-logic | 19.145480 | 21.487844 | 17.749418 | 17.40% | 7.29% | -4 | -2 |
| Ibex | State/clock protected | 19.145480 | 24.139121 | 18.798488 | 22.12% | 1.81% | -16 | -2 |

Interpretation: timing-regret guarded repair reduces timing-weighted crossing in all tested design-scenario cases relative to the previous guarded repair, while remaining slightly better than the TritonPart initial assignment on the same timing metric.
