# ASA-on-Native Phase-1 Rollup

This rollup summarizes the strong-baseline diagnostic experiments where ASA-RV3D refines native OpenROAD/TritonPart timing-aware assignments.

## Result

- Primary comparable pass cases: 2
- Boundary / inconclusive cases: 1
- Primary designs: riscv32i, picorv32
- Boundary designs: scr1_core_tuned

## Interpretation

The current evidence supports ASA-RV3D as a bounded, domain-aware refinement layer on top of a strong timing-aware TritonPart baseline for the primary comparable cases. SCR1 is retained as a boundary case because the native timing-aware baseline is already slightly outside the reconstructed strict area-balance window.

## Candidate Rows

### riscv32i

- Status: primary_comparable_pass
- Candidate: cut_regret_0p050000
- Area pass: true
- Crossing regret vs native: 0.043478
- Timing-weighted regret vs native: 0.000928
- P_avg_cut regret vs native: 0.000000
- P_wst_cut delta vs native: 0.000000
- Scenario gain: 15.350335
- Note: Small cut-regret candidate preserves area/path quality with positive scenario gain.

### picorv32

- Status: primary_comparable_pass
- Candidate: prefix_027
- Area pass: true
- Crossing regret vs native: -0.060345
- Timing-weighted regret vs native: -0.010366
- P_avg_cut regret vs native: 0.000000
- P_wst_cut delta vs native: 0.000000
- Scenario gain: 1435.177127
- Note: Area-feasible prefix improves cut and timing-weighted crossing while preserving path-cut metrics.

### scr1_core_tuned

- Status: boundary_inconclusive_native_area_window
- Candidate: cut_regret_0p050000
- Area pass: false
- Crossing regret vs native: 0.044118
- Timing-weighted regret vs native: -0.005083
- P_avg_cut regret vs native: 
- P_wst_cut delta vs native: 0.000000
- Scenario gain: 92.144299
- Note: Native timing-aware baseline is already slightly outside the reconstructed strict 48/52 area window; retain as boundary evidence, not primary comparable success.
