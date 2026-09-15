#!/usr/bin/env python3
"""Scenario-aware RISC-V 3D tier partitioning.

Stage 4 of the ASA-RV3D plan.

This script is the first partitioner that directly optimizes a 3D integration
scenario instead of only evaluating existing assignments. It reads:

  - gate-level features,
  - architecture mapping results,
  - graph-context scores when available,
  - configs/3d_integration_scenarios.yaml.

It writes a scenario-specific tier assignment and comparison tables.

The method is still a lightweight research prototype. It uses greedy local
refinement, not a production EDA partitioner.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


TIERS = ("tier0", "tier1")

SCENARIO_TIER_POLICY = {
    "logic_on_logic": {
        "tier0": {"clock_reset", "pipeline_state", "csr", "decode_control", "fetch", "trap_debug", "generated_control"},
        "tier1": {"execute_alu", "multdiv", "load_store", "register_file", "generated_datapath"},
    },
    "memory_near_logic": {
        "tier0": {"fetch", "decode_control", "csr", "trap_debug", "clock_reset", "pipeline_state", "generated_control"},
        "tier1": {"load_store", "register_file", "execute_alu", "multdiv", "generated_datapath"},
    },
    "control_datapath_split": {
        "tier0": {"fetch", "decode_control", "csr", "trap_debug", "clock_reset", "pipeline_state", "generated_control"},
        "tier1": {"execute_alu", "multdiv", "load_store", "register_file", "generated_datapath"},
    },
    "state_and_clock_protected": {
        "tier0": {"clock_reset", "pipeline_state", "csr", "trap_debug", "fetch", "decode_control", "generated_control"},
        "tier1": {"execute_alu", "multdiv", "load_store", "register_file", "generated_datapath"},
    },
}

DEFAULT_SCENARIOS = {
    "state_and_clock_protected": {
        "cost_weights": {
            "base_crossing": 1.0,
            "high_fanout": 0.30,
            "control_datapath_boundary": 1.5,
            "architecture_criticality": 1.8,
            "semantic_uncertainty": 1.2,
            "instance_balance": 0.50,
            "weight_balance": 0.10,
        },
        "architecture_unit_multipliers": {
            "clock_reset": 3.0,
            "pipeline_state": 2.4,
            "register_file": 2.2,
            "csr": 2.0,
            "trap_debug": 1.8,
            "generated_control": 1.0,
            "generated_datapath": 1.0,
        },
    }
}


@dataclass(frozen=True)
class Instance:
    instance: str
    module: str
    cell_type: str
    cell_category: str
    architecture_unit: str
    semantic_group: str
    criticality_weight: float
    mapping_confidence: float
    graph_context_score: float
    net_count: int
    nets: tuple[str, ...]

    @property
    def weight(self) -> int:
        base = 2 if self.cell_category == "sequential" else 1
        return base + min(self.net_count, 8)


@dataclass
class State:
    assignment: dict[str, str]
    tier_counts: Counter[str]
    tier_weights: Counter[str]
    net_tiers: dict[str, Counter[str]]


@dataclass(frozen=True)
class NetInfo:
    net: str
    instances: tuple[str, ...]
    factor: float
    total_connections: int
    units: tuple[str, ...]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def parse_scenarios(path: Path) -> dict[str, dict[str, dict[str, float]]]:
    if not path.exists():
        return DEFAULT_SCENARIOS

    scenarios: dict[str, dict[str, dict[str, float]]] = {}
    in_scenarios = False
    current = None
    current_map = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "scenarios:":
            in_scenarios = True
            continue
        if not in_scenarios:
            continue
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            current = stripped[:-1]
            scenarios[current] = {"cost_weights": {}, "architecture_unit_multipliers": {}}
            current_map = None
            continue
        if current is None:
            continue
        if line.startswith("    ") and not line.startswith("      ") and stripped.endswith(":"):
            key = stripped[:-1]
            current_map = key if key in {"cost_weights", "architecture_unit_multipliers"} else None
            continue
        if current_map and line.startswith("      ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            try:
                scenarios[current][current_map][key.strip()] = float(scalar(value))
            except ValueError:
                pass
    return scenarios or DEFAULT_SCENARIOS


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except ValueError:
        return default


def load_context_scores(features_dir: Path) -> dict[str, float]:
    path = features_dir / "graph_context_scores.csv"
    if not path.exists():
        return {}
    scores = {}
    for row in read_csv(path):
        scores[row["instance"]] = f(row, "semantic_context_score", 0.5)
    return scores


def load_instances(features_dir: Path) -> list[Instance]:
    features = {row["instance"]: row for row in read_csv(features_dir / "instance_features.csv")}
    mapping_path = features_dir / "architecture_mapping_instances.csv"
    mapping = {row["instance"]: row for row in read_csv(mapping_path)}
    context = load_context_scores(features_dir)

    instances: list[Instance] = []
    for inst, row in features.items():
        mapped = mapping.get(inst, {})
        nets = tuple(net for net in row.get("nets", "").split(";") if net)
        instances.append(
            Instance(
                instance=inst,
                module=row.get("module", ""),
                cell_type=row.get("cell_type", row.get("cell", "")),
                cell_category=row.get("cell_category", row.get("category", "")),
                architecture_unit=mapped.get("architecture_unit", "unclassified"),
                semantic_group=mapped.get("semantic_group", "infrastructure"),
                criticality_weight=f(mapped, "criticality_weight", 1.0),
                mapping_confidence=f(mapped, "mapping_confidence", 0.5),
                graph_context_score=context.get(inst, 0.5),
                net_count=int(row.get("net_count", "0") or 0),
                nets=nets,
            )
        )
    return instances


def net_crossing_cost(counts: Counter[str], factor: float) -> float:
    if counts["tier0"] and counts["tier1"]:
        return min(counts["tier0"], counts["tier1"]) * factor
    return 0.0


def build_net_info(
    instances: list[Instance],
    scenario: dict[str, dict[str, float]],
) -> dict[str, NetInfo]:
    by_net: dict[str, list[Instance]] = defaultdict(list)
    for inst in instances:
        for net in inst.nets:
            by_net[net].append(inst)

    weights = scenario["cost_weights"]
    multipliers = scenario["architecture_unit_multipliers"]
    info: dict[str, NetInfo] = {}

    for net, connected in by_net.items():
        groups = {inst.semantic_group for inst in connected}
        units = {inst.architecture_unit for inst in connected}
        total = len(connected)
        confidence = sum(inst.mapping_confidence * inst.graph_context_score for inst in connected) / total if total else 0.5
        max_arch = max(
            inst.criticality_weight * multipliers.get(inst.architecture_unit, 1.0)
            for inst in connected
        )
        factor = weights.get("base_crossing", 1.0)
        factor += max(0, total - 8) * weights.get("high_fanout", 0.0)
        if {"control", "datapath"}.issubset(groups):
            factor += weights.get("control_datapath_boundary", 0.0)
        factor += max_arch * weights.get("architecture_criticality", 1.0)
        factor += (1.0 - confidence) * weights.get("semantic_uncertainty", 0.0)
        info[net] = NetInfo(
            net=net,
            instances=tuple(inst.instance for inst in connected),
            factor=factor,
            total_connections=total,
            units=tuple(sorted(units)),
        )
    return info


def make_state(instances: list[Instance], assignment: dict[str, str]) -> State:
    by_name = {inst.instance: inst for inst in instances}
    counts: Counter[str] = Counter()
    weights: Counter[str] = Counter()
    net_tiers: dict[str, Counter[str]] = defaultdict(Counter)
    for name, tier in assignment.items():
        inst = by_name[name]
        counts[tier] += 1
        weights[tier] += inst.weight
        for net in inst.nets:
            net_tiers[net][tier] += 1
    return State(dict(assignment), counts, weights, net_tiers)


def generic_balance(instances: list[Instance]) -> dict[str, str]:
    loads = Counter({"tier0": 0, "tier1": 0})
    assignment = {}
    for inst in sorted(instances, key=lambda item: (-item.weight, item.instance)):
        tier = "tier0" if loads["tier0"] <= loads["tier1"] else "tier1"
        assignment[inst.instance] = tier
        loads[tier] += inst.weight
    return assignment


def preferred_tier(unit: str, scenario_name: str) -> str | None:
    policy = SCENARIO_TIER_POLICY.get(scenario_name, SCENARIO_TIER_POLICY["logic_on_logic"])
    if unit in policy["tier0"]:
        return "tier0"
    if unit in policy["tier1"]:
        return "tier1"
    return None


def scenario_initial(instances: list[Instance], scenario_name: str) -> dict[str, str]:
    loads = Counter({"tier0": 0, "tier1": 0})
    assignment = {}
    for inst in sorted(
        instances,
        key=lambda item: (-item.mapping_confidence, -item.criticality_weight, item.architecture_unit, item.instance),
    ):
        tier = preferred_tier(inst.architecture_unit, scenario_name)
        if tier is None:
            tier = "tier0" if loads["tier0"] <= loads["tier1"] else "tier1"
        assignment[inst.instance] = tier
        loads[tier] += inst.weight
    return assignment


def balance_ratio(counter: Counter[str]) -> float:
    high = max(counter["tier0"], counter["tier1"])
    low = min(counter["tier0"], counter["tier1"])
    return low / high if high else 1.0


def net_cost_total(state: State, net_info: dict[str, NetInfo]) -> float:
    return sum(net_crossing_cost(state.net_tiers[net], info.factor) for net, info in net_info.items())


def preference_penalty(inst: Instance, tier: str, scenario_name: str, architecture_weight: float, context_weight: float) -> float:
    pref = preferred_tier(inst.architecture_unit, scenario_name)
    if pref is None or pref == tier:
        return 0.0
    context_scale = 0.2 + 0.8 * inst.graph_context_score
    confidence = inst.mapping_confidence * ((1.0 - context_weight) + context_weight * context_scale)
    return architecture_weight * inst.weight * inst.criticality_weight * confidence


def preference_total(instances: list[Instance], assignment: dict[str, str], scenario_name: str, architecture_weight: float, context_weight: float) -> float:
    return sum(preference_penalty(inst, assignment[inst.instance], scenario_name, architecture_weight, context_weight) for inst in instances)


def objective(
    state: State,
    instances: list[Instance],
    net_info: dict[str, NetInfo],
    scenario: dict[str, dict[str, float]],
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
) -> float:
    weights = scenario["cost_weights"]
    crossing = net_cost_total(state, net_info)
    instance_balance = (1.0 - balance_ratio(state.tier_counts)) * weights.get("instance_balance", 0.0) * 1000.0
    weight_balance = (1.0 - balance_ratio(state.tier_weights)) * weights.get("weight_balance", 0.0) * 1000.0
    pref = preference_total(instances, state.assignment, scenario_name, architecture_weight, context_weight)
    return crossing + instance_balance + weight_balance + pref


def move_satisfies_balance(
    state: State,
    inst: Instance,
    old_tier: str,
    new_tier: str,
    min_instance_balance: float,
    min_weight_balance: float,
) -> bool:
    counts = Counter(state.tier_counts)
    counts[old_tier] -= 1
    counts[new_tier] += 1
    weights = Counter(state.tier_weights)
    weights[old_tier] -= inst.weight
    weights[new_tier] += inst.weight

    before_i = balance_ratio(state.tier_counts)
    before_w = balance_ratio(state.tier_weights)
    after_i = balance_ratio(counts)
    after_w = balance_ratio(weights)
    if after_i >= min_instance_balance and after_w >= min_weight_balance:
        return True
    improves_i = after_i >= before_i
    improves_w = after_w >= before_w
    strictly = after_i > before_i or after_w > before_w
    return improves_i and improves_w and strictly


def move_gain(
    state: State,
    inst: Instance,
    new_tier: str,
    net_info: dict[str, NetInfo],
    scenario: dict[str, dict[str, float]],
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
) -> float:
    old_tier = state.assignment[inst.instance]
    if old_tier == new_tier:
        return 0.0

    before = 0.0
    after = 0.0
    for net in inst.nets:
        info = net_info[net]
        counts = state.net_tiers[net]
        before += net_crossing_cost(counts, info.factor)
        new_counts = Counter(counts)
        new_counts[old_tier] -= 1
        new_counts[new_tier] += 1
        after += net_crossing_cost(new_counts, info.factor)

    weights = scenario["cost_weights"]
    before_counts = state.tier_counts
    before_weights = state.tier_weights
    after_counts = Counter(before_counts)
    after_counts[old_tier] -= 1
    after_counts[new_tier] += 1
    after_weights = Counter(before_weights)
    after_weights[old_tier] -= inst.weight
    after_weights[new_tier] += inst.weight

    before += (1.0 - balance_ratio(before_counts)) * weights.get("instance_balance", 0.0) * 1000.0
    before += (1.0 - balance_ratio(before_weights)) * weights.get("weight_balance", 0.0) * 1000.0
    after += (1.0 - balance_ratio(after_counts)) * weights.get("instance_balance", 0.0) * 1000.0
    after += (1.0 - balance_ratio(after_weights)) * weights.get("weight_balance", 0.0) * 1000.0

    before += preference_penalty(inst, old_tier, scenario_name, architecture_weight, context_weight)
    after += preference_penalty(inst, new_tier, scenario_name, architecture_weight, context_weight)
    return before - after


def apply_move(state: State, inst: Instance, new_tier: str) -> None:
    old_tier = state.assignment[inst.instance]
    state.assignment[inst.instance] = new_tier
    state.tier_counts[old_tier] -= 1
    state.tier_counts[new_tier] += 1
    state.tier_weights[old_tier] -= inst.weight
    state.tier_weights[new_tier] += inst.weight
    for net in inst.nets:
        state.net_tiers[net][old_tier] -= 1
        state.net_tiers[net][new_tier] += 1


def refine(
    instances: list[Instance],
    initial: dict[str, str],
    net_info: dict[str, NetInfo],
    scenario: dict[str, dict[str, float]],
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
    max_passes: int,
    max_moves_per_pass: int,
    min_gain: float,
    min_instance_balance: float,
    min_weight_balance: float,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    state = make_state(instances, initial)
    trace = []
    candidates = sorted(instances, key=lambda item: (-item.weight, -item.criticality_weight, item.instance))

    for pass_id in range(1, max_passes + 1):
        moves = 0
        total_gain = 0.0
        for inst in candidates:
            old = state.assignment[inst.instance]
            new = "tier1" if old == "tier0" else "tier0"
            if not move_satisfies_balance(state, inst, old, new, min_instance_balance, min_weight_balance):
                continue
            gain = move_gain(state, inst, new, net_info, scenario, scenario_name, architecture_weight, context_weight)
            if gain <= min_gain:
                continue
            apply_move(state, inst, new)
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
                    "instance_balance_after": f"{balance_ratio(state.tier_counts):.6f}",
                    "weight_balance_after": f"{balance_ratio(state.tier_weights):.6f}",
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
                "instance_balance_after": f"{balance_ratio(state.tier_counts):.6f}",
                "weight_balance_after": f"{balance_ratio(state.tier_weights):.6f}",
            }
        )
        if moves == 0:
            break
    return state.assignment, trace


def summarize_assignment(
    name: str,
    assignment: dict[str, str],
    instances: list[Instance],
    net_info: dict[str, NetInfo],
    scenario: dict[str, dict[str, float]],
    scenario_name: str,
    architecture_weight: float,
    context_weight: float,
) -> dict[str, object]:
    state = make_state(instances, assignment)
    crossing = 0
    crossing_nets = 0
    total_connections = 0
    scenario_cost = 0.0
    for net, info in net_info.items():
        counts = state.net_tiers[net]
        total_connections += counts["tier0"] + counts["tier1"]
        if counts["tier0"] and counts["tier1"]:
            crossing_nets += 1
            crossing += min(counts["tier0"], counts["tier1"])
            scenario_cost += net_crossing_cost(counts, info.factor)
    pref = preference_total(instances, assignment, scenario_name, architecture_weight, context_weight)
    obj = objective(state, instances, net_info, scenario, scenario_name, architecture_weight, context_weight)
    return {
        "strategy": name,
        "total_instances": state.tier_counts["tier0"] + state.tier_counts["tier1"],
        "tier0_instances": state.tier_counts["tier0"],
        "tier1_instances": state.tier_counts["tier1"],
        "instance_balance_ratio": f"{balance_ratio(state.tier_counts):.6f}",
        "tier0_weight": state.tier_weights["tier0"],
        "tier1_weight": state.tier_weights["tier1"],
        "weight_balance_ratio": f"{balance_ratio(state.tier_weights):.6f}",
        "crossing_nets": crossing_nets,
        "crossing_connections_proxy": crossing,
        "total_net_connections": total_connections,
        "crossing_connection_fraction": f"{crossing / total_connections if total_connections else 0.0:.6f}",
        "scenario_proxy_cost": f"{scenario_cost:.6f}",
        "architecture_preference_penalty": f"{pref:.6f}",
        "scenario_objective": f"{obj:.6f}",
    }


def write_assignment(path: Path, assignment: dict[str, str], instances: list[Instance]) -> None:
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
    write_csv(path, rows, ["instance", "tier", "architecture_unit", "semantic_group", "weight"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--scenarios", type=Path, default=Path("configs/3d_integration_scenarios.yaml"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--architecture-weight", type=float, default=0.35)
    parser.add_argument("--context-weight", type=float, default=1.0)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--max-moves-per-pass", type=int, default=4000)
    parser.add_argument("--min-gain", type=float, default=0.001)
    parser.add_argument("--min-instance-balance", type=float, default=0.80)
    parser.add_argument("--min-weight-balance", type=float, default=0.92)
    args = parser.parse_args()

    scenarios = parse_scenarios(args.scenarios)
    if args.scenario not in scenarios:
        raise SystemExit(f"unknown scenario {args.scenario}; available: {', '.join(sorted(scenarios))}")
    scenario = scenarios[args.scenario]

    instances = load_instances(args.features_dir)
    net_info = build_net_info(instances, scenario)

    generic = generic_balance(instances)
    initial = scenario_initial(instances, args.scenario)
    refined, trace = refine(
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

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_assignment(args.output_dir / "generic_balance_assignment.csv", generic, instances)
    write_assignment(args.output_dir / "scenario_initial_assignment.csv", initial, instances)
    write_assignment(args.output_dir / "scenario_aware_assignment.csv", refined, instances)

    comparison = [
        summarize_assignment("generic_balance", generic, instances, net_info, scenario, args.scenario, args.architecture_weight, args.context_weight),
        summarize_assignment("scenario_initial", initial, instances, net_info, scenario, args.scenario, args.architecture_weight, args.context_weight),
        summarize_assignment("scenario_aware", refined, instances, net_info, scenario, args.scenario, args.architecture_weight, args.context_weight),
    ]
    generic_obj = float(comparison[0]["scenario_objective"])
    for row in comparison:
        cur = float(row["scenario_objective"])
        row["reduction_vs_generic_objective"] = f"{(generic_obj - cur) / generic_obj if generic_obj else 0.0:.6f}"

    write_csv(
        args.output_dir / "partition_comparison.csv",
        comparison,
        [
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
            "reduction_vs_generic_objective",
        ],
    )
    write_csv(
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
        "max_passes": args.max_passes,
        "max_moves_per_pass": args.max_moves_per_pass,
        "min_instance_balance": args.min_instance_balance,
        "min_weight_balance": args.min_weight_balance,
        "outputs": [
            "generic_balance_assignment.csv",
            "scenario_initial_assignment.csv",
            "scenario_aware_assignment.csv",
            "partition_comparison.csv",
            "local_refinement_trace.csv",
            "manifest.json",
        ],
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(args.output_dir / "partition_comparison.csv")
    print(args.output_dir / "local_refinement_trace.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
