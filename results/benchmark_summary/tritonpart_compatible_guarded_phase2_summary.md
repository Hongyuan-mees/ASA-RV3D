# TritonPart-Compatible ASA Guarded Phase 2

This summary reports the online guarded-repair prototype, where each accepted move must preserve OpenROAD-compatible area balance, bounded cut regret, and path-cut guards.

## Result

- Admissible Phase-2 cases: 2 / 3
- Admissible designs: picorv32, riscv32i

## Case Summary

### picorv32

- Status: admissible_phase2
- Final area pass: true
- Cut regret: -0.338150
- Timing-weighted regret vs native: -0.040062
- P_avg_cut regret vs native: 0.000000
- P_wst_cut delta vs native: 0.000000
- Scenario gain: 5686.246863
- Note: Online guarded repair result.

### riscv32i

- Status: admissible_phase2
- Final area pass: true
- Cut regret: 0.039130
- Timing-weighted regret vs native: -0.029007
- P_avg_cut regret vs native: -0.146341
- P_wst_cut delta vs native: -1.000000
- Scenario gain: 2398.510713
- Note: Online guarded repair result.

### scr1_core_tuned

- Status: boundary_inconclusive_native_area_window
- Final area pass: false
- Cut regret: 0.044118
- Timing-weighted regret vs native: -0.005083
- P_avg_cut regret vs native: 
- P_wst_cut delta vs native: 0.000000
- Scenario gain: 92.144299
- Note: Native timing-aware baseline is already slightly outside the reconstructed strict 48/52 area window; retain as boundary evidence, not primary comparable success.
