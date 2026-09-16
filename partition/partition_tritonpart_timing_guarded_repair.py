#!/usr/bin/env python3
"""Timing-aware guarded ASA-RV3D repair over a TritonPart assignment.

This version keeps TritonPart as the strong connectivity baseline and adds a
timing-context risk term to the guarded repair layer. The repair objective uses:

  scenario objective
+ physical-context crossing penalty
+ timing-context crossing penalty

The goal is to prevent scenario/physical repair from increasing timing-critical
crossings while preserving explicit balance guardrails.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_assignment(path: Path) -> dict[str, str]:
    return {row["instance"]: row["tier"] for row in read_csv(path)}


def load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_timing_scores(features_dir: Path) -> dict[str, float]:
    path = features_dir / "timing_context_scores.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run evaluation/extract_timing_context.py first.")
    scores = {}
    for row in read_csv(path):
        try:
            scores[row["instance"]] = float(row.get("timing_context_score", "0") or 0.0)
        except ValueError:
            scores[row["instance"]] = 0.0
    return scores


def build_net_risk(net_info, scores: dict[str, float]) -> dict[str, float]:
    risks = {}
    for net, info in net_info.items():
        vals = [scores.get(inst, 0.0) for inst in info.instances]
        if not vals:
            risks[net] = 0.0
            continue
        risks[net] = 0.70 * max(vals) + 0.30 * (sum(vals) / len(vals))
    return risks


def combine_risk(
    physical_risk: dict[str, float],
    timing_risk: dict[str, float],
    physical_weight: float,
    timing_weight: float,
) -> dict[str, float]:
    nets = set(physical_risk) | set(timing_risk)
    return {
        net: physical_weight * physical_risk.get(net, 0.0) + timing_weight * timing_risk.get(net, 0.0)
        for net in nets
    }


def crossing_cost_for_risk(state, net_risk: dict[str, float]) -> float:
    total = 0.0
    for net, counts in state.net_tiers.items():
        if counts["tier0"] and counts["tier1"]:
            total += min(counts["tier0"], counts["tier1"]) * net_risk.get(net, 0.0)
    return total


def summarize(
    name: str,
    assignment: dict[str, str],
    base,
    instances,
    net_info,
    scenario,
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
    physical_risk: dict[str, float],
    timing_risk: dict[str, float],
    combined_risk: dict[str, float],
    physical_weight: float,
    timing_weight: float,
) -> dict[str, object]:
    row = base.summarize_assignment(
        name,
        assignment,
        instances,
        net_info,
        scenario,
        scenario_name,
        architecture_weight,
        context_weight,
    )
    state = base.make_state(instances, assignment)
    physical_penalty = crossing_cost_for_risk(state, physical_risk)
    timing_penalty = crossing_cost_for_risk(state, timing_risk)
    combined_penalty = crossing_cost_for_risk(state, combined_risk)
    scenario_objective = float(row["scenario_objective"])

    row["physical_context_crossing_penalty"] = f"{physical_penalty:.6f}"
    row["timing_context_crossing_penalty"] = f"{timing_penalty:.6f}"
    row["combined_repair_crossing_penalty"] = f"{combined_penalty:.6f}"
    row["physical_weight"] = f"{physical_weight:.6f}"
    row["timing_weight"] = f"{timing_weight:.6f}"
    row["timing_augmented_objective"] = f"{scenario_objective + physical_weight * physical_penalty + timing_weight * timing_penalty:.6f}"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features-dir", type=Path)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--tritonpart-assignment", type=Path)
    parser.add_argument("--scenarios", type=Path, default=Path("configs/3d_integration_scenarios.yaml"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--architecture-weight", type=float, default=0.35)
    parser.add_argument("--context-weight", type=float, default=1.0)
    parser.add_argument("--physical-weight", type=float, default=1.0)
    parser.add_argument("--timing-weight", type=float, default=1.0)
    parser.add_argument("--max-scenario-regret-per-move", type=float, default=0.05)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--max-moves-per-pass", type=int, default=4000)
    parser.add_argument("--min-gain", type=float, default=0.001)
    parser.add_argument("--guard-min-instance-balance", type=float, default=0.90)
    parser.add_argument("--guard-min-weight-balance", type=float, default=0.90)
    args = parser.parse_args()

    partition_dir = Path("partition")
    sys.path.insert(0, str(partition_dir.resolve()))
    base = load_module("partition_scenario_aware", partition_dir / "partition_scenario_aware.py")
    guarded = load_module("partition_v4b_physical_guarded", partition_dir / "partition_v4b_physical_guarded.py")

    features_dir = args.features_dir or Path("results") / f"{args.design}_features"
    tritonpart_assignment_path = (
        args.tritonpart_assignment
        or Path("results") / f"{args.design}_tritonpart_baseline" / "tritonpart_assignment.csv"
    )
    output_dir = (
        args.output_dir
        or Path("results") / f"{args.design}_tritonpart_timing_guarded_repair" / args.scenario
    )

    scenarios = base.parse_scenarios(args.scenarios)
    if args.scenario not in scenarios:
        raise SystemExit(f"unknown scenario {args.scenario}; available: {', '.join(sorted(scenarios))}")
    scenario = scenarios[args.scenario]

    instances = base.load_instances(features_dir)
    known_instances = {inst.instance for inst in instances}
    initial = load_assignment(tritonpart_assignment_path)
    missing = known_instances - set(initial)
    extra = set(initial) - known_instances
    if missing or extra:
        raise ValueError(f"assignment mismatch: missing={len(missing)} extra={len(extra)}")

    net_info = base.build_net_info(instances, scenario)
    physical_scores = guarded.load_physical_scores(features_dir)
    timing_scores = load_timing_scores(features_dir)

    physical_risk = guarded.build_net_physical_risk(net_info, physical_scores)
    timing_risk = build_net_risk(net_info, timing_scores)
    combined_risk = combine_risk(physical_risk, timing_risk, args.physical_weight, args.timing_weight)

    initial_state = base.make_state(instances, initial)
    initial_instance_balance = base.balance_ratio(initial_state.tier_counts)
    initial_weight_balance = base.balance_ratio(initial_state.tier_weights)
    effective_min_instance_balance = min(args.guard_min_instance_balance, initial_instance_balance)
    effective_min_weight_balance = min(args.guard_min_weight_balance, initial_weight_balance)

    repaired, trace = guarded.guarded_refine(
        instances=instances,
        initial=initial,
        net_info=net_info,
        net_risk=combined_risk,
        scenario=scenario,
        scenario_name=args.scenario,
        architecture_weight=args.architecture_weight,
        context_weight=args.context_weight,
        physical_weight=1.0,
        max_passes=args.max_passes,
        max_moves_per_pass=args.max_moves_per_pass,
        min_gain=args.min_gain,
        min_instance_balance=effective_min_instance_balance,
        min_weight_balance=effective_min_weight_balance,
        max_scenario_regret_per_move=args.max_scenario_regret_per_move,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    guarded.write_assignment(output_dir / "tritonpart_initial_assignment.csv", initial, instances)
    guarded.write_assignment(output_dir / "tritonpart_timing_guarded_repair_assignment.csv", repaired, instances)

    comparison = [
        summarize(
            "tritonpart_initial",
            initial,
            base,
            instances,
            net_info,
            scenario,
            args.scenario,
            args.architecture_weight,
            args.context_weight,
            physical_risk,
            timing_risk,
            combined_risk,
            args.physical_weight,
            args.timing_weight,
        ),
        summarize(
            "tritonpart_timing_guarded_repair",
            repaired,
            base,
            instances,
            net_info,
            scenario,
            args.scenario,
            args.architecture_weight,
            args.context_weight,
            physical_risk,
            timing_risk,
            combined_risk,
            args.physical_weight,
            args.timing_weight,
        ),
    ]

    initial_obj = float(comparison[0]["timing_augmented_objective"])
    for row in comparison:
        cur = float(row["timing_augmented_objective"])
        row["reduction_vs_tritonpart_initial"] = f"{(initial_obj - cur) / initial_obj if initial_obj else 0.0:.6f}"
        row["effective_min_instance_balance"] = f"{effective_min_instance_balance:.6f}"
        row["effective_min_weight_balance"] = f"{effective_min_weight_balance:.6f}"

    fields = [
        "strategy",
        "total_instances",
        "tier0_instances",
        "tier1_instances",
        "instance_balance_ratio",
        "tier0_weight",
        "tier1_weight",
        "weight_balance_ratio",
        "crossing_nets",
        "crossing_connections_proxy",
        "total_net_connections",
        "crossing_connection_fraction",
        "scenario_proxy_cost",
        "architecture_preference_penalty",
        "scenario_objective",
        "physical_context_crossing_penalty",
        "timing_context_crossing_penalty",
        "combined_repair_crossing_penalty",
        "physical_weight",
        "timing_weight",
        "timing_augmented_objective",
        "reduction_vs_tritonpart_initial",
        "effective_min_instance_balance",
        "effective_min_weight_balance",
    ]
    base.write_csv(output_dir / "partition_comparison.csv", comparison, fields)

    trace_fields = [
        "pass",
        "move_index",
        "instance",
        "architecture_unit",
        "from_tier",
        "to_tier",
        "gain",
        "scenario_gain",
        "physical_gain",
        "instance_balance_after",
        "weight_balance_after",
    ]
    base.write_csv(output_dir / "local_refinement_trace.csv", trace, trace_fields)

    manifest = {
        "design": args.design,
        "scenario": args.scenario,
        "features_dir": str(features_dir),
        "tritonpart_assignment": str(tritonpart_assignment_path),
        "output_dir": str(output_dir),
        "physical_weight": args.physical_weight,
        "timing_weight": args.timing_weight,
        "effective_min_instance_balance": effective_min_instance_balance,
        "effective_min_weight_balance": effective_min_weight_balance,
        "outputs": [
            "tritonpart_initial_assignment.csv",
            "tritonpart_timing_guarded_repair_assignment.csv",
            "partition_comparison.csv",
            "local_refinement_trace.csv",
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(output_dir / "partition_comparison.csv")
    print(output_dir / "local_refinement_trace.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
