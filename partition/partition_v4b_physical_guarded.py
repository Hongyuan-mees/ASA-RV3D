#!/usr/bin/env python3
"""Guarded physical-context-aware RISC-V 3D tier partitioning.

Stage 5 of the ASA-RV3D plan.

This partitioner extends ``partition_scenario_aware.py`` with a conservative
two-stage physical-context guard:

  1. build the normal scenario-aware assignment;
  2. accept physical-context moves only when they do not meaningfully damage
     the scenario objective.

The goal is not to make the physical score dominate. The goal is to preserve
the scenario-aware result and use physical context only as a disciplined
tie-breaker / small corrective signal.

Required input in ``--features-dir``:

  - instance_features.csv
  - architecture_mapping_instances.csv
  - graph_context_scores.csv, optional
  - physical_context_scores.csv

The physical score has already been coverage-gated, so units with poor DEF
observability contribute weakly instead of injecting false physical evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import partition_scenario_aware as base


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        raw = row.get(key, "")
        if raw == "":
            return default
        return float(raw)
    except ValueError:
        return default


def load_physical_scores(features_dir: Path) -> dict[str, float]:
    path = features_dir / "physical_context_scores.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run evaluation/physical_context_score.py before partition_v4_physical_context.py."
        )
    scores = {}
    for row in read_csv(path):
        scores[row["instance"]] = f(row, "physical_context_score", 0.0)
    return scores


def build_net_physical_risk(
    net_info: dict[str, base.NetInfo],
    physical_scores: dict[str, float],
) -> dict[str, float]:
    risks = {}
    for net, info in net_info.items():
        scores = [physical_scores.get(inst, 0.0) for inst in info.instances]
        if not scores:
            risks[net] = 0.0
            continue
        max_score = max(scores)
        mean_score = sum(scores) / len(scores)
        risks[net] = 0.65 * max_score + 0.35 * mean_score
    return risks


def physical_crossing_cost(counts: Counter[str], net_risk: float) -> float:
    if counts["tier0"] and counts["tier1"]:
        return min(counts["tier0"], counts["tier1"]) * net_risk
    return 0.0


def physical_cost_total(state: base.State, net_risk: dict[str, float]) -> float:
    return sum(physical_crossing_cost(counts, net_risk.get(net, 0.0)) for net, counts in state.net_tiers.items())


def augmented_objective(
    state: base.State,
    instances: list[base.Instance],
    net_info: dict[str, base.NetInfo],
    net_risk: dict[str, float],
    scenario: dict[str, dict[str, float]],
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
    physical_weight: float,
) -> float:
    scenario_objective = base.objective(
        state,
        instances,
        net_info,
        scenario,
        scenario_name,
        architecture_weight,
        context_weight,
    )
    return scenario_objective + physical_weight * physical_cost_total(state, net_risk)


def physical_move_delta(
    state: base.State,
    inst: base.Instance,
    new_tier: str,
    net_risk: dict[str, float],
) -> float:
    old_tier = state.assignment[inst.instance]
    before = 0.0
    after = 0.0
    for net in inst.nets:
        counts = state.net_tiers[net]
        risk = net_risk.get(net, 0.0)
        before += physical_crossing_cost(counts, risk)
        new_counts = Counter(counts)
        new_counts[old_tier] -= 1
        new_counts[new_tier] += 1
        after += physical_crossing_cost(new_counts, risk)
    return before - after


def move_gain(
    state: base.State,
    inst: base.Instance,
    new_tier: str,
    net_info: dict[str, base.NetInfo],
    net_risk: dict[str, float],
    scenario: dict[str, dict[str, float]],
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
    physical_weight: float,
) -> float:
    scenario_gain = base.move_gain(
        state,
        inst,
        new_tier,
        net_info,
        scenario,
        scenario_name,
        architecture_weight,
        context_weight,
    )
    return scenario_gain + physical_weight * physical_move_delta(state, inst, new_tier, net_risk)


def guarded_refine(
    instances: list[base.Instance],
    initial: dict[str, str],
    net_info: dict[str, base.NetInfo],
    net_risk: dict[str, float],
    scenario: dict[str, dict[str, float]],
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
    physical_weight: float,
    max_passes: int,
    max_moves_per_pass: int,
    min_gain: float,
    min_instance_balance: float,
    min_weight_balance: float,
    max_scenario_regret_per_move: float,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    state = base.make_state(instances, initial)
    trace = []
    candidates = sorted(
        instances,
        key=lambda item: (-item.weight, -item.criticality_weight, -item.graph_context_score, item.instance),
    )

    for pass_id in range(1, max_passes + 1):
        moves = 0
        total_gain = 0.0
        for inst in candidates:
            old = state.assignment[inst.instance]
            new = "tier1" if old == "tier0" else "tier0"
            if not base.move_satisfies_balance(state, inst, old, new, min_instance_balance, min_weight_balance):
                continue
            scenario_gain = base.move_gain(
                state,
                inst,
                new,
                net_info,
                scenario,
                scenario_name,
                architecture_weight,
                context_weight,
            )
            physical_gain = physical_move_delta(state, inst, new, net_risk)
            gain = scenario_gain + physical_weight * physical_gain
            if gain <= min_gain:
                continue
            if scenario_gain < -max_scenario_regret_per_move:
                continue
            base.apply_move(state, inst, new)
            moves += 1
            total_gain += gain
            trace.append(
                {
                    "pass": pass_id,
                    "move_index": moves,
                    "instance": inst.instance,
                    "architecture_unit": inst.architecture_unit,
                    "from_tier": old,
                    "to_tier": new,
                    "gain": f"{gain:.6f}",
                    "scenario_gain": f"{scenario_gain:.6f}",
                    "physical_gain": f"{physical_gain:.6f}",
                    "instance_balance_after": f"{base.balance_ratio(state.tier_counts):.6f}",
                    "weight_balance_after": f"{base.balance_ratio(state.tier_weights):.6f}",
                }
            )
            if moves >= max_moves_per_pass:
                break
        trace.append(
            {
                "pass": pass_id,
                "move_index": "summary",
                "instance": "",
                "architecture_unit": "",
                "from_tier": "",
                "to_tier": "",
                "gain": f"{total_gain:.6f}",
                "scenario_gain": "",
                "physical_gain": "",
                "instance_balance_after": f"{base.balance_ratio(state.tier_counts):.6f}",
                "weight_balance_after": f"{base.balance_ratio(state.tier_weights):.6f}",
            }
        )
        if moves == 0:
            break
    return state.assignment, trace


def summarize_assignment(
    name: str,
    assignment: dict[str, str],
    instances: list[base.Instance],
    net_info: dict[str, base.NetInfo],
    net_risk: dict[str, float],
    scenario: dict[str, dict[str, float]],
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
    physical_weight: float,
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
    physical_penalty = physical_cost_total(state, net_risk)
    row["physical_context_crossing_penalty"] = f"{physical_penalty:.6f}"
    row["physical_weight"] = f"{physical_weight:.6f}"
    row["physical_augmented_objective"] = f"{float(row['scenario_objective']) + physical_weight * physical_penalty:.6f}"
    return row


def write_assignment(path: Path, assignment: dict[str, str], instances: list[base.Instance]) -> None:
    by_name = {inst.instance: inst for inst in instances}
    rows = []
    for name in sorted(assignment):
        inst = by_name[name]
        rows.append(
            {
                "instance": name,
                "tier": assignment[name],
                "architecture_unit": inst.architecture_unit,
                "semantic_group": inst.semantic_group,
                "weight": inst.weight,
            }
        )
    base.write_csv(path, rows, ["instance", "tier", "architecture_unit", "semantic_group", "weight"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--scenarios", type=Path, default=Path("configs/3d_integration_scenarios.yaml"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--architecture-weight", type=float, default=0.35)
    parser.add_argument("--context-weight", type=float, default=1.0)
    parser.add_argument("--physical-weight", type=float, default=1.0)
    parser.add_argument("--max-scenario-regret-per-move", type=float, default=0.05)
    parser.add_argument("--guard-min-instance-balance", type=float)
    parser.add_argument("--guard-min-weight-balance", type=float)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--max-moves-per-pass", type=int, default=4000)
    parser.add_argument("--min-gain", type=float, default=0.001)
    parser.add_argument("--min-instance-balance", type=float, default=0.80)
    parser.add_argument("--min-weight-balance", type=float, default=0.92)
    args = parser.parse_args()

    scenarios = base.parse_scenarios(args.scenarios)
    if args.scenario not in scenarios:
        raise SystemExit(f"unknown scenario {args.scenario}; available: {', '.join(sorted(scenarios))}")
    scenario = scenarios[args.scenario]

    instances = base.load_instances(args.features_dir)
    net_info = base.build_net_info(instances, scenario)
    physical_scores = load_physical_scores(args.features_dir)
    net_risk = build_net_physical_risk(net_info, physical_scores)

    generic = base.generic_balance(instances)
    initial = base.scenario_initial(instances, args.scenario)
    scenario_aware, scenario_trace = base.refine(
        instances=instances,
        initial=initial,
        net_info=net_info,
        scenario=scenario,
        scenario_name=args.scenario,
        architecture_weight=args.architecture_weight,
        context_weight=args.context_weight,
        max_passes=args.max_passes,
        max_moves_per_pass=args.max_moves_per_pass,
        min_gain=args.min_gain,
        min_instance_balance=args.min_instance_balance,
        min_weight_balance=args.min_weight_balance,
    )
    refined, trace = guarded_refine(
        instances=instances,
        initial=scenario_aware,
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
        min_instance_balance=(
            args.guard_min_instance_balance
            if args.guard_min_instance_balance is not None
            else args.min_instance_balance
        ),
        min_weight_balance=(
            args.guard_min_weight_balance
            if args.guard_min_weight_balance is not None
            else args.min_weight_balance
        ),
        max_scenario_regret_per_move=args.max_scenario_regret_per_move,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_assignment(args.output_dir / "generic_balance_assignment.csv", generic, instances)
    write_assignment(args.output_dir / "scenario_initial_assignment.csv", initial, instances)
    write_assignment(args.output_dir / "scenario_aware_assignment.csv", scenario_aware, instances)
    write_assignment(args.output_dir / "physical_guarded_assignment.csv", refined, instances)

    comparison = [
        summarize_assignment(
            "generic_balance",
            generic,
            instances,
            net_info,
            net_risk,
            scenario,
            args.scenario,
            args.architecture_weight,
            args.context_weight,
            args.physical_weight,
        ),
        summarize_assignment(
            "scenario_initial",
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
        summarize_assignment(
            "scenario_aware",
            scenario_aware,
            instances,
            net_info,
            net_risk,
            scenario,
            args.scenario,
            args.architecture_weight,
            args.context_weight,
            args.physical_weight,
        ),
        summarize_assignment(
            "physical_guarded",
            refined,
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
    generic_augmented = float(comparison[0]["physical_augmented_objective"])
    for row in comparison:
        cur = float(row["physical_augmented_objective"])
        row["reduction_vs_generic_physical_augmented_objective"] = (
            f"{(generic_augmented - cur) / generic_augmented if generic_augmented else 0.0:.6f}"
        )

    comparison_fields = [
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
        "reduction_vs_generic_physical_augmented_objective",
    ]
    base.write_csv(args.output_dir / "partition_comparison.csv", comparison, comparison_fields)
    base.write_csv(
        args.output_dir / "local_refinement_trace.csv",
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
        "features_dir": str(args.features_dir),
        "scenario": args.scenario,
        "scenarios": str(args.scenarios),
        "output_dir": str(args.output_dir),
        "architecture_weight": args.architecture_weight,
        "context_weight": args.context_weight,
        "physical_weight": args.physical_weight,
        "max_scenario_regret_per_move": args.max_scenario_regret_per_move,
        "max_passes": args.max_passes,
        "max_moves_per_pass": args.max_moves_per_pass,
        "min_instance_balance": args.min_instance_balance,
        "min_weight_balance": args.min_weight_balance,
        "guard_min_instance_balance": args.guard_min_instance_balance,
        "guard_min_weight_balance": args.guard_min_weight_balance,
        "outputs": [
            "generic_balance_assignment.csv",
            "scenario_initial_assignment.csv",
            "scenario_aware_assignment.csv",
            "physical_guarded_assignment.csv",
            "partition_comparison.csv",
            "local_refinement_trace.csv",
            "manifest.json",
        ],
        "note": "Physical term is coverage-gated and guarded against scenario-objective regressions.",
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(args.output_dir / "partition_comparison.csv")
    print(args.output_dir / "local_refinement_trace.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
