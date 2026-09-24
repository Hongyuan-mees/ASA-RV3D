# ASA-on-Native Bounded-Regret Phase 1

Design: picorv32
Scenario: state_and_clock_protected

## Main Finding

A small cut-regret budget preserves TritonPart-compatible feasibility and timing-path quality while exposing architecture/scenario benefit.

## Recommended Phase-1 Candidate

- Case: cut_regret_0p05
- Native area balance pass: false
- Cut regret: -35.84%
- Timing-weighted crossing regret: -6.07%
- P_avg_cut regret: 20.00%
- P_wst_cut delta: 0.000000
- Scenario gain: 5961.593985

## Interpretation

The unconstrained ASA-on-native repair was too aggressive in raw cutsize. The bounded replay shows that a small prefix of the same repair trace already provides scenario gain while preserving native area feasibility and timing-path cuts. This supports the bounded-regret refinement direction, but the next implementation should enforce cut-regret directly during candidate move acceptance rather than relying on trace replay.
