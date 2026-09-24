# ASA-on-Native Bounded-Regret Phase 1

Design: scr1_core_tuned
Scenario: state_and_clock_protected

## Main Finding

This report checks whether a bounded ASA replay can expose architecture/scenario benefit while preserving TritonPart-compatible area feasibility and timing-path quality.

## Recommended Phase-1 Candidate

No bounded-replay candidate passes the strict TritonPart-compatible area window in this summary.

## Closest Non-Passing Candidate

- Case: cut_regret_0p050000
- Area balance pass: false
- Tier0 area fraction: 0.520973
- Tier1 area fraction: 0.479027
- Cut regret: 4.41%
- Timing-weighted crossing regret: -0.51%
- P_avg_cut regret: 
- Scenario gain: 92.144299

## Interpretation

The bounded replay is a diagnostic, not the final algorithm. A candidate is paper-usable only if it preserves the native TritonPart area-balance constraint and keeps cut/timing-path regret within the selected budget. If the replay improves scenario metrics but fails area balance, the next step is an area-feasible bounded replay or a direct area-aware acceptance guard.
