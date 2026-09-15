#!/usr/bin/env python3
"""Graph-context-aware ASA-RV3D partition experiment.

This script reuses the partition_v2 implementation and changes only the
architecture-penalty term:

    v2: penalty = architecture_weight * instance_weight * confidence
    v3: penalty = architecture_weight * instance_weight * confidence
                  * semantic_context_score

The intuition is simple: when the graph neighborhood agrees with an instance's
semantic class, the architecture preference should be trusted more. When the
graph context is weak or ambiguous, crossing and balance are allowed to drive
the move more strongly.

The script is intentionally a small wrapper so v2 and v3 remain directly
comparable.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import partition_v2 as v2


CONTEXT_SCORES: dict[str, float] = {}
CONTEXT_WEIGHT = 1.0
CONTEXT_FLOOR = 0.20


def read_context_scores(path: Path) -> dict[str, float]:
    scores: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            scores[row["instance"]] = float(row["semantic_context_score"])
    return scores


def context_scaled_architecture_penalty(inst: v2.Instance, tier: str, weights: v2.ObjectiveWeights) -> float:
    preferred = v2.ARCH_TIER_POLICY.get(inst.architecture_class)
    if preferred is None or tier == preferred:
        return 0.0

    confidence_scale = min(max(inst.confidence, 1), 10) / 10.0
    context_score = CONTEXT_SCORES.get(inst.instance, 1.0)
    context_scale = CONTEXT_FLOOR + (1.0 - CONTEXT_FLOOR) * context_score
    blended_scale = (1.0 - CONTEXT_WEIGHT) + CONTEXT_WEIGHT * context_scale

    return weights.architecture * inst.weight * confidence_scale * blended_scale


def patch_balance_repair() -> None:
    """Patch v2 balance logic if this checkout predates balance repair.

    Some older v2 versions required every candidate move to immediately satisfy
    hard balance thresholds. The repaired behavior allows monotonic balance
    improvement when the current assignment is still infeasible.
    """

    def repaired_move_satisfies_balance(
        state: v2.State,
        inst: v2.Instance,
        old_tier: str,
        new_tier: str,
        min_instance_balance: float,
        min_weight_balance: float,
    ) -> bool:
        after_counts = v2.Counter(state.tier_counts)
        after_counts[old_tier] -= 1
        after_counts[new_tier] += 1

        after_weights = v2.Counter(state.tier_weights)
        after_weights[old_tier] -= inst.weight
        after_weights[new_tier] += inst.weight

        before_instance = v2.balance_ratio(state.tier_counts)
        before_weight = v2.balance_ratio(state.tier_weights)
        after_instance = v2.balance_ratio(after_counts)
        after_weight = v2.balance_ratio(after_weights)

        if after_instance >= min_instance_balance and after_weight >= min_weight_balance:
            return True

        improves_instance = after_instance >= before_instance
        improves_weight = after_weight >= before_weight
        strictly_improves = after_instance > before_instance or after_weight > before_weight
        return improves_instance and improves_weight and strictly_improves

    v2.move_satisfies_balance = repaired_move_satisfies_balance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--context-scores", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--crossing-weight", type=float, default=1.0)
    parser.add_argument("--instance-balance-weight", type=float, default=0.4)
    parser.add_argument("--weight-balance-weight", type=float, default=0.02)
    parser.add_argument("--architecture-weight", type=float, default=0.4)
    parser.add_argument("--context-weight", type=float, default=1.0)
    parser.add_argument("--context-floor", type=float, default=0.20)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--max-moves-per-pass", type=int, default=4000)
    parser.add_argument("--min-gain", type=float, default=0.001)
    parser.add_argument("--min-instance-balance", type=float, default=0.80)
    parser.add_argument("--min-weight-balance", type=float, default=0.95)
    args = parser.parse_args()

    global CONTEXT_SCORES, CONTEXT_WEIGHT, CONTEXT_FLOOR
    context_path = args.context_scores or (args.features_dir / "graph_context_scores.csv")
    CONTEXT_SCORES = read_context_scores(context_path)
    CONTEXT_WEIGHT = args.context_weight
    CONTEXT_FLOOR = args.context_floor

    patch_balance_repair()
    v2.architecture_penalty = context_scaled_architecture_penalty

    v2_args = argparse.Namespace(
        features_dir=args.features_dir,
        output_dir=args.output_dir,
        crossing_weight=args.crossing_weight,
        instance_balance_weight=args.instance_balance_weight,
        weight_balance_weight=args.weight_balance_weight,
        architecture_weight=args.architecture_weight,
        max_passes=args.max_passes,
        max_moves_per_pass=args.max_moves_per_pass,
        min_gain=args.min_gain,
        min_instance_balance=args.min_instance_balance,
        min_weight_balance=args.min_weight_balance,
    )
    manifest = v2.run(v2_args)

    manifest.update(
        {
            "method": "architecture_score_v3_context",
            "context_scores": str(context_path),
            "context_weight": args.context_weight,
            "context_floor": args.context_floor,
            "architecture_penalty": "confidence_scaled_by_semantic_context_score",
            "note": "Strategy names in CSVs are inherited from partition_v2 for direct comparability.",
        }
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
