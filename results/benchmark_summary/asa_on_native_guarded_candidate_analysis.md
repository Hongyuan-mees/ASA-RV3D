# ASA-on-Native Guarded Candidate Selection

This diagnostic applies one fixed guard rule to existing ASA-on-native candidates.

## Guard Rule

- area_balance_pass must be true
- crossing regret <= 5.00%
- timing-weighted regret <= 1.00%
- P_avg_cut regret <= 0.00%
- P_wst_cut delta <= 0.000000

## Result

- Admissible cases: 2 / 3
- Admissible designs: riscv32i, picorv32

### riscv32i

- Status: admissible
- Selected case: cut_regret_0p050000
- Cut regret: 0.043478
- Timing-weighted regret: 0.000928
- P_avg_cut regret: 0.000000
- P_wst_cut delta: 0.000000
- Scenario gain: 15.350335
- Reject reasons: 

### picorv32

- Status: admissible
- Selected case: prefix_027
- Cut regret: -0.060345
- Timing-weighted regret: -0.010366
- P_avg_cut regret: 0.000000
- P_wst_cut delta: 0.000000
- Scenario gain: 1435.177127
- Reject reasons: 

### scr1_core_tuned

- Status: no_admissible_candidate
- Selected case: 
- Cut regret: 
- Timing-weighted regret: 
- P_avg_cut regret: 
- P_wst_cut delta: 
- Scenario gain: 
- Reject reasons: area_balance;cut_regret
