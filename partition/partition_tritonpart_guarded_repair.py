#!/usr/bin/env python3
"""Guarded ASA-RV3D repair over a TritonPart assignment.

TritonPart provides a strong connectivity-first 2-way hypergraph partition.
This script treats that result as the initial assignment and applies the same
ASA-RV3D guarded physical-context refinement used by v4b.

The purpose is not to beat TritonPart on raw cut by moving many vertices. The
purpose is to test whether architecture/scenario/physical context can safely
repair a mature hypergraph partition under explicit balance guardrails.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
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
        raise ImportError(f"Could not load {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


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
        or Path("results") / f"{args.design}_tritonpart_guarded_repair" / args.scenario
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
    net_risk = guarded.build_net_physical_risk(net_info, physical_scores)

    repaired, trace = guarded.guarded_refine(
        instances=instances,
        initial=initial,
        net_info=net_info,
        net_risk=net_risk,
        scenario=scenario,
        scenario_name=args.scenario,
        architecture_weight=args.architecture_weight,
        context_weight=args.context_weight,
        physical_weight=args.physical_weight,
        max_passes=args.max_passes,
        max_moves_per_pass=args.max_moves_per_pass,
        min_gain=args.min_gain,
        min_instance_balance=args.guard_min_instance_balance,
        min_weight_balance=args.guard_min_weight_balance,
        max_scenario_regret_per_move=args.max_scenario_regret_per_move,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    guarded.write_assignment(output_dir / "tritonpart_initial_assignment.csv", initial, instances)
    guarded.write_assignment(output_dir / "tritonpart_guarded_repair_assignment.csv", repaired, instances)

    comparison = [
        guarded.summarize_assignment(
            "tritonpart_initial",
            initial,
            instances,
            net_info,
            net_risk,
            scenario,
            args.scenario,
            args.architecture_weight,
            args.context_weight,
            args.physical_weight,
        ),
        guarded.summarize_assignment(
            "tritonpart_guarded_repair",
            repaired,
            instances,
            net_info,
            net_risk,
            scenario,
            args.scenario,
            args.architecture_weight,
            args.context_weight,
            args.physical_weight,
        ),
    ]
    initial_obj = float(comparison[0]["physical_augmented_objective"])
    for row in comparison:
        cur = float(row["physical_augmented_objective"])
        row["reduction_vs_tritonpart_initial"] = f"{(initial_obj - cur) / initial_obj if initial_obj else 0.0:.6f}"

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
        "physical_weight",
        "physical_augmented_objective",
        "reduction_vs_tritonpart_initial",
    ]
    base.write_csv(output_dir / "partition_comparison.csv", comparison, fields)
    base.write_csv(
        output_dir / "local_refinement_trace.csv",
        trace,
        [
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
        ],
    )
    manifest = {
        "design": args.design,
        "features_dir": str(features_dir),
        "scenario": args.scenario,
        "tritonpart_assignment": str(tritonpart_assignment_path),
        "output_dir": str(output_dir),
        "guard_min_instance_balance": args.guard_min_instance_balance,
        "guard_min_weight_balance": args.guard_min_weight_balance,
        "max_scenario_regret_per_move": args.max_scenario_regret_per_move,
        "outputs": [
            "tritonpart_initial_assignment.csv",
            "tritonpart_guarded_repair_assignment.csv",
            "partition_comparison.csv",
            "local_refinement_trace.csv",
            "manifest.json",
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(output_dir / "partition_comparison.csv")
    print(output_dir / "local_refinement_trace.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
